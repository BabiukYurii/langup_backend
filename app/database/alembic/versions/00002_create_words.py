"""create words table

Revision ID: 00002
Revises: 00001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00002"
down_revision = "00001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "words",
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lemma", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("part_of_speech", sa.String(length=32), nullable=True),
        sa.Column("phonetic", sa.String(length=128), nullable=True),
        sa.Column("definitions", postgresql.JSONB(), nullable=True),
        sa.Column("frequency_rank", sa.Integer(), nullable=True),
        sa.Column("base_difficulty", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("lemma", "language", name="uq_word_lemma_language"),
    )
    op.create_index("ix_words_uuid", "words", ["uuid"])
    op.create_index("ix_words_lemma", "words", ["lemma"])
    op.create_index("ix_words_language", "words", ["language"])
    op.create_index("ix_words_created_at", "words", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_words_created_at", table_name="words")
    op.drop_index("ix_words_language", table_name="words")
    op.drop_index("ix_words_lemma", table_name="words")
    op.drop_index("ix_words_uuid", table_name="words")
    op.drop_table("words")
