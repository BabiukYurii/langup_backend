"""create sources, word_contexts, user_words

Revision ID: 00004
Revises: 00003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00004"
down_revision = "00003"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), server_default="WEB_PAGE", nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("raw_html_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("user_id", "url", name="uq_source_user_url"),
    )
    op.create_index("ix_sources_user_id", "sources", ["user_id"])
    op.create_index("ix_sources_domain", "sources", ["domain"])
    op.create_index("ix_sources_created_at", "sources", ["created_at"])

    op.create_table(
        "word_contexts",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("word_uuid", _UUID, nullable=False),
        sa.Column("source_uuid", _UUID, nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("surface_form", sa.String(length=128), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("context_before", sa.Text(), nullable=True),
        sa.Column("context_after", sa.Text(), nullable=True),
        sa.Column("dom_path", sa.Text(), nullable=True),
        sa.Column("ai_sense", postgresql.JSONB(), nullable=True),
        sa.Column("ai_difficulty", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["word_uuid"], ["words.uuid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_uuid"], ["sources.uuid"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index("ix_word_contexts_word_uuid", "word_contexts", ["word_uuid"])
    op.create_index("ix_word_contexts_user_id", "word_contexts", ["user_id"])
    op.create_index("ix_word_contexts_created_at", "word_contexts", ["created_at"])

    op.create_table(
        "user_words",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word_uuid", _UUID, nullable=False),
        sa.Column("mastery_level", sa.String(length=16), server_default="NEW", nullable=False),
        sa.Column("ease_factor", sa.Numeric(precision=4, scale=2), server_default="2.5", nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("repetitions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("correct_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("incorrect_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_uuid"], ["words.uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("user_id", "word_uuid", name="uq_user_word"),
    )
    op.create_index("ix_user_words_user_id", "user_words", ["user_id"])
    op.create_index("ix_user_words_word_uuid", "user_words", ["word_uuid"])
    op.create_index("ix_user_words_due_at", "user_words", ["due_at"])
    op.create_index("ix_user_words_created_at", "user_words", ["created_at"])


def downgrade() -> None:
    op.drop_table("user_words")
    op.drop_table("word_contexts")
    op.drop_table("sources")
