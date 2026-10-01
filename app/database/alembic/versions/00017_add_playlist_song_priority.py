"""add priority to playlist_songs

Revision ID: 00017
Revises: 00016
"""

import sqlalchemy as sa
from alembic import op

revision = "00017"
down_revision = "00016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playlist_songs", sa.Column("priority", sa.Integer(), server_default="0", nullable=False))
    op.create_index("ix_playlist_songs_priority", "playlist_songs", ["priority"])
    # Existing rows stay at 0, which is exactly the old behaviour: warming
    # order decided entirely by playlist position.


def downgrade() -> None:
    op.drop_index("ix_playlist_songs_priority", table_name="playlist_songs")
    op.drop_column("playlist_songs", "priority")
