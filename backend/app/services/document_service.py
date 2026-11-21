"""Document service: accepts uploads, extracts text, enqueues async ingestion."""
import hashlib
import io
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidRequest,
    NotFound,
    PayloadTooLarge,
    PermissionDenied,
    UnsupportedMediaType,
)
from app.core.logging import get_logger
from app.db.models import Document, DocumentStatus, User, UserRole
from app.db.repositories.documents import DocumentRepository
from app.services.knowledge_base_service import KnowledgeBaseService
from app.workers.queue import enqueue_ingestion, enqueue_reindex

logger = get_logger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "text",
    "text/markdown": "markdown",
    "text/html": "html",
}


def extract_document(data: bytes, source_type: str) -> tuple[str, dict]:
    if source_type == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        properties = reader.metadata
        metadata = {
            key: str(getattr(properties, property_name))
            for key, property_name in {
                "title": "title",
                "author": "author",
                "subject": "subject",
                "creator": "creator",
            }.items()
            if properties and getattr(properties, property_name, None)
        }
        metadata["page_count"] = len(reader.pages)
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return text, metadata
    if source_type == "docx":
        from docx import Document as WordDocument

        document = WordDocument(io.BytesIO(data))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
        tables = [
            "\n".join("\t".join(cell.text.strip() for cell in row.cells) for row in table.rows)
            for table in document.tables
        ]
        text = "\n\n".join(part for part in [*paragraphs, *tables] if part)
        properties = document.core_properties
        metadata = {
            key: value
            for key, value in {
                "title": properties.title,
                "author": properties.author,
                "subject": properties.subject,
                "keywords": properties.keywords,
            }.items()
            if value
        }
        metadata["paragraph_count"] = len(document.paragraphs)
        metadata["table_count"] = len(document.tables)
        return text, metadata
    if source_type == "html":
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
        metadata = {}
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()
        author = soup.find("meta", attrs={"name": "author"})
        if author and author.get("content"):
            metadata["author"] = author["content"]
        return soup.get_text(separator="\n"), metadata
    return data.decode("utf-8", errors="replace"), {}


def extract_text(data: bytes, source_type: str) -> str:
    return extract_document(data, source_type)[0]


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.documents = DocumentRepository(db)

    async def ingest_upload(
        self, user: User, file: UploadFile, knowledge_base_id: UUID | None = None
    ) -> Document:
        if knowledge_base_id is not None:
            await KnowledgeBaseService(self.db).require_owned(user, knowledge_base_id)
        content_type = file.content_type or ""
        if content_type not in ALLOWED_TYPES:
            raise UnsupportedMediaType(f"Unsupported content type: {content_type or 'unknown'}")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise PayloadTooLarge("File exceeds 20 MB limit")

        source_type = ALLOWED_TYPES[content_type]
        text, extracted_metadata = extract_document(data, source_type)
        if not text.strip():
            raise InvalidRequest("The uploaded document contains no extractable text")
        content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = await self.documents.get_by_content_sha256(
            user.id, content_sha256, knowledge_base_id
        )
        if existing:
            return existing

        return await self._create_and_enqueue(
            user,
            title=file.filename or "untitled",
            source_type=source_type,
            text=text,
            metadata={
                "filename": file.filename or "",
                "content_type": content_type,
                **extracted_metadata,
            },
            content_sha256=content_sha256,
            knowledge_base_id=knowledge_base_id,
        )

    async def ingest_text(
        self,
        user: User,
        *,
        title: str,
        content: str,
        metadata: dict,
        knowledge_base_id: UUID | None = None,
    ) -> Document:
        if not content.strip():
            raise InvalidRequest("Document text cannot be empty")
        if knowledge_base_id is not None:
            await KnowledgeBaseService(self.db).require_owned(user, knowledge_base_id)
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = await self.documents.get_by_content_sha256(
            user.id, content_sha256, knowledge_base_id
        )
        if existing:
            return existing
        return await self._create_and_enqueue(
            user,
            title=title,
            source_type="text",
            text=content,
            metadata=metadata,
            content_sha256=content_sha256,
            knowledge_base_id=knowledge_base_id,
        )

    async def _create_and_enqueue(
        self,
        user: User,
        *,
        title: str,
        source_type: str,
        text: str,
        metadata: dict | None = None,
        content_sha256: str | None = None,
        knowledge_base_id: UUID | None = None,
    ) -> Document:
        try:
            doc = await self.documents.create(
                owner_id=user.id,
                title=title,
                source_type=source_type,
                metadata=metadata or {},
                content_sha256=content_sha256,
                knowledge_base_id=knowledge_base_id,
            )
        except IntegrityError:
            await self.db.rollback()
            if content_sha256:
                existing = await self.documents.get_by_content_sha256(
                    user.id, content_sha256, knowledge_base_id
                )
                if existing:
                    return existing
            raise
        await self.db.commit()  # make the row visible to the worker before enqueueing
        await enqueue_ingestion(str(doc.id), text)
        logger.info("document_enqueued", document_id=str(doc.id), title=title)
        return doc

    async def list_documents(
        self, user: User, knowledge_base_id: UUID | None = None
    ) -> list[Document]:
        if knowledge_base_id is not None:
            await KnowledgeBaseService(self.db).require_owned(user, knowledge_base_id)
        return await self.documents.list_for_user(
            user.id, knowledge_base_id=knowledge_base_id
        )

    async def delete_document(self, user: User, doc_id: UUID) -> None:
        doc = await self.documents.get(doc_id)
        if doc is None:
            raise NotFound("Document not found")
        if doc.owner_id != user.id and user.role != UserRole.admin:
            raise PermissionDenied("Not your document")
        from ai.rag.vectorstore import get_vector_store

        await get_vector_store().delete_document(str(doc.id))
        await self.db.delete(doc)

    async def reindex_document(self, user: User, doc_id: UUID) -> Document:
        doc = await self.documents.get(doc_id)
        if doc is None:
            raise NotFound("Document not found")
        if doc.owner_id != user.id:
            raise PermissionDenied("Not your document")
        if doc.status in (DocumentStatus.pending, DocumentStatus.processing):
            raise InvalidRequest("Document is already being processed")
        if doc.chunk_count == 0:
            raise InvalidRequest("Document has no chunks to re-index")
        previous_status = doc.status
        await self.documents.set_status(doc.id, DocumentStatus.pending)
        await self.db.commit()
        try:
            await enqueue_reindex(str(doc.id))
        except Exception:
            await self.documents.set_status(doc.id, previous_status)
            await self.db.commit()
            raise
        return doc

    async def move_document(
        self, user: User, doc_id: UUID, knowledge_base_id: UUID | None
    ) -> Document:
        doc = await self.documents.get(doc_id)
        if doc is None:
            raise NotFound("Document not found")
        if doc.owner_id != user.id and user.role != UserRole.admin:
            raise PermissionDenied("Not your document")
        if doc.status != DocumentStatus.ready:
            raise InvalidRequest("Only ready documents can be moved")
        if doc.knowledge_base_id == knowledge_base_id:
            return doc
        if knowledge_base_id is not None:
            await KnowledgeBaseService(self.db).require_owned(user, knowledge_base_id)
        if doc.content_sha256:
            duplicate = await self.documents.get_by_content_sha256(
                doc.owner_id, doc.content_sha256, knowledge_base_id
            )
            if duplicate and duplicate.id != doc.id:
                raise InvalidRequest(
                    "This knowledge base already contains the same document content"
                )

        previous_knowledge_base_id = doc.knowledge_base_id
        doc.knowledge_base_id = knowledge_base_id
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise InvalidRequest(
                "This knowledge base already contains the same document content"
            ) from exc

        from ai.rag.vectorstore import get_vector_store

        store = get_vector_store()
        try:
            await store.set_document_owner(
                str(doc.id),
                str(doc.owner_id),
                str(knowledge_base_id) if knowledge_base_id else None,
            )
            await self.db.commit()
        except Exception as exc:
            await self.db.rollback()
            try:
                await store.set_document_owner(
                    str(doc.id),
                    str(doc.owner_id),
                    str(previous_knowledge_base_id) if previous_knowledge_base_id else None,
                )
            except Exception as rollback_exc:
                logger.error(
                    "document_scope_rollback_failed",
                    document_id=str(doc.id),
                    update_error=str(exc),
                    rollback_error=str(rollback_exc),
                )
                raise RuntimeError(
                    "Document move failed and its vector scope could not be restored"
                ) from rollback_exc
            raise
        return doc
