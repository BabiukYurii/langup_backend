"""create song_warm_states

Revision ID: 00015
Revises: 00014
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00015"
down_revision = "00014"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "song_warm_states",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("song_uuid", _UUID, nullable=False),
        sa.Column("target_language", sa.String(length=8), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("words_warmed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.ForeignKeyConstraint(["song_uuid"], ["songs.uuid"], ondelete="CASCADE"),
        sa.UniqueConstraint("song_uuid", "target_language", name="uq_song_warm_state"),
    )
    op.create_index("ix_song_warm_states_song_uuid", "song_warm_states", ["song_uuid"])
    op.create_index("ix_song_warm_states_target_language", "song_warm_states", ["target_language"])
    op.create_index("ix_song_warm_states_completed_at", "song_warm_states", ["completed_at"])


def downgrade() -> None:
    # Dropping this only forgets progress: the warmed translations and clips
    # stay in their own caches, so a rebuilt table finds the work already done
    # and completes each pair on its first pass.
    op.drop_index("ix_song_warm_states_completed_at", table_name="song_warm_states")
    op.drop_index("ix_song_warm_states_target_language", table_name="song_warm_states")
    op.drop_index("ix_song_warm_states_song_uuid", table_name="song_warm_states")
    op.drop_table("song_warm_states")
