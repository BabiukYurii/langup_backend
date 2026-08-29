"""create audio_clips

Revision ID: 00013
Revises: 00012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00013"
down_revision = "00012"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "audio_clips",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("voice", sa.String(length=32), nullable=False),
        sa.Column("object_key", sa.String(length=256), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("hash", name="uq_audio_clip_hash"),
    )
    op.create_index("ix_audio_clips_hash", "audio_clips", ["hash"])
    op.create_index("ix_audio_clips_language", "audio_clips", ["language"])


def downgrade() -> None:
    # The blobs in object storage outlive this table. That is deliberate: they
    # are addressed by a deterministic hash, so re-running the upgrade re-uses
    # whatever is still stored instead of re-synthesizing it.
    op.drop_index("ix_audio_clips_language", table_name="audio_clips")
    op.drop_index("ix_audio_clips_hash", table_name="audio_clips")
    op.drop_table("audio_clips")
