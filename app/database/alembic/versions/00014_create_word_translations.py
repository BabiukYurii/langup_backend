"""create word_translations

Revision ID: 00014
Revises: 00013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00014"
down_revision = "00013"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "word_translations",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("word", sa.String(length=128), nullable=False),
        sa.Column("source_language", sa.String(length=8), nullable=False),
        sa.Column("target_language", sa.String(length=8), nullable=False),
        # A hash of the line, never the line: the lyrics themselves are parsed
        # fresh every time and deliberately not stored anywhere.
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("translation", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint(
            "word",
            "source_language",
            "target_language",
            "context_hash",
            name="uq_word_translation",
        ),
    )
    op.create_index("ix_word_translations_word", "word_translations", ["word"])
    op.create_index("ix_word_translations_source_language", "word_translations", ["source_language"])
    op.create_index("ix_word_translations_target_language", "word_translations", ["target_language"])
    op.create_index("ix_word_translations_context_hash", "word_translations", ["context_hash"])


def downgrade() -> None:
    op.drop_index("ix_word_translations_context_hash", table_name="word_translations")
    op.drop_index("ix_word_translations_target_language", table_name="word_translations")
    op.drop_index("ix_word_translations_source_language", table_name="word_translations")
    op.drop_index("ix_word_translations_word", table_name="word_translations")
    op.drop_table("word_translations")
