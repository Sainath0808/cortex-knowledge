"""Add user-owned knowledge bases and document membership.

Revision ID: 0003_knowledge_bases
Revises: 0002_document_content_hash
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_knowledge_bases"
down_revision = "0002_document_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_knowledge_bases_owner_name"),
    )
    op.create_index("ix_knowledge_bases_owner_id", "knowledge_bases", ["owner_id"])
    op.add_column(
        "documents",
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"])
    op.drop_constraint("uq_documents_owner_content_sha256", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_owner_kb_content_sha256",
        "documents",
        ["owner_id", "knowledge_base_id", "content_sha256"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_owner_kb_content_sha256", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_owner_content_sha256", "documents", ["owner_id", "content_sha256"]
    )
    op.drop_index("ix_documents_knowledge_base_id", table_name="documents")
    op.drop_column("documents", "knowledge_base_id")
    op.drop_index("ix_knowledge_bases_owner_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
