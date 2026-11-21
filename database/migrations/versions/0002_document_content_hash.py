"""Add per-owner document content hashes for duplicate detection.

Revision ID: 0002_document_content_hash
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_document_content_hash"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_sha256", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_documents_owner_content_sha256", "documents", ["owner_id", "content_sha256"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_owner_content_sha256", "documents", type_="unique")
    op.drop_column("documents", "content_sha256")
