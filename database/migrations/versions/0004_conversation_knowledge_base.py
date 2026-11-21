"""Persist knowledge-base scope on chat conversations.

Revision ID: 0004_conversation_knowledge_base
Revises: 0003_knowledge_bases
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_conversation_knowledge_base"
down_revision = "0003_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_knowledge_base_id",
        "conversations",
        ["knowledge_base_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_knowledge_base_id", table_name="conversations")
    op.drop_column("conversations", "knowledge_base_id")
