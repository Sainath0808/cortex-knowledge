import io

from docx import Document as WordDocument

from app.db.models import User
from app.db.repositories.documents import DocumentRepository
from app.services.document_service import extract_document


def test_docx_extraction_includes_paragraphs_tables_and_metadata():
    document = WordDocument()
    document.core_properties.title = "Employee Guide"
    document.add_paragraph("Vacation policy")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Annual leave"
    table.rows[0].cells[1].text = "22 days"
    buffer = io.BytesIO()
    document.save(buffer)

    text, metadata = extract_document(buffer.getvalue(), "docx")

    assert "Vacation policy" in text
    assert "Annual leave\t22 days" in text
    assert metadata["title"] == "Employee Guide"
    assert metadata["table_count"] == 1


async def test_content_hash_lookup_is_scoped_to_owner(db_session):
    first_user = User(email="first@example.com", hashed_password="hash")
    second_user = User(email="second@example.com", hashed_password="hash")
    db_session.add_all([first_user, second_user])
    await db_session.flush()
    repository = DocumentRepository(db_session)

    document = await repository.create(
        owner_id=first_user.id,
        title="Policy",
        source_type="text",
        metadata={},
        content_sha256="a" * 64,
    )

    assert await repository.get_by_content_sha256(first_user.id, "a" * 64) == document
    assert await repository.get_by_content_sha256(second_user.id, "a" * 64) is None
