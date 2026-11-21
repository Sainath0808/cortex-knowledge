"""Document endpoints: upload, ingest raw text, list, delete."""

from uuid import UUID

from fastapi import APIRouter, UploadFile

from app.api.deps import DB, CurrentUser
from app.schemas.api import DocumentOut, IngestTextRequest, KnowledgeBaseMoveRequest
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    knowledge_base_id: UUID | None = None,
):
    """Accept PDF, DOCX, TXT, Markdown, or HTML; processing is async — poll status."""
    return await DocumentService(db).ingest_upload(user, file, knowledge_base_id)


@router.post("/text", response_model=DocumentOut, status_code=202)
async def ingest_text(payload: IngestTextRequest, user: CurrentUser, db: DB):
    return await DocumentService(db).ingest_text(
        user,
        title=payload.title,
        content=payload.content,
        metadata=payload.metadata,
        knowledge_base_id=payload.knowledge_base_id,
    )


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: CurrentUser, db: DB, knowledge_base_id: UUID | None = None):
    return await DocumentService(db).list_documents(user, knowledge_base_id)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, user: CurrentUser, db: DB):
    await DocumentService(db).delete_document(user, doc_id)


@router.post("/{doc_id}/reindex", response_model=DocumentOut, status_code=202)
async def reindex_document(doc_id: UUID, user: CurrentUser, db: DB):
    return await DocumentService(db).reindex_document(user, doc_id)


@router.patch("/{doc_id}/knowledge-base", response_model=DocumentOut)
async def move_document(doc_id: UUID, payload: KnowledgeBaseMoveRequest, user: CurrentUser, db: DB):
    return await DocumentService(db).move_document(user, doc_id, payload.knowledge_base_id)
