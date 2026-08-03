"""add language to exercises

Revision ID: 00011
Revises: 00010
"""

import sqlalchemy as sa
from alembic import op

revision = "00011"
down_revision = "00010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("language", sa.String(length=8), nullable=True))
    op.create_index("ix_exercises_language", "exercises", ["language"])
    # Backfill from the exercise's word so the existing pool is filterable too.
    op.execute(
        "UPDATE exercises e SET language = w.language "
        "FROM words w WHERE e.word_uuid = w.uuid AND e.language IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_exercises_language", table_name="exercises")
    op.drop_column("exercises", "language")
