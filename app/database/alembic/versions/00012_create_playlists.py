"""create playlists, songs, playlist_songs

Revision ID: 00012
Revises: 00011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00012"
down_revision = "00011"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")
_JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "songs",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("artist", sa.String(length=256), server_default="", nullable=False),
        sa.Column("spotify_id", sa.String(length=64), nullable=True),
        sa.Column("match_key", sa.String(length=600), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("lemmas", _JSONB, nullable=True),
        sa.Column("lyrics_found", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("match_key", name="uq_song_match_key"),
    )
    op.create_index("ix_songs_match_key", "songs", ["match_key"])
    op.create_index("ix_songs_language", "songs", ["language"])

    op.create_table(
        "playlists",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("spotify_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index("ix_playlists_user_id", "playlists", ["user_id"])

    op.create_table(
        "playlist_songs",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("playlist_uuid", _UUID, nullable=False),
        sa.Column("song_uuid", _UUID, nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["playlist_uuid"], ["playlists.uuid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["song_uuid"], ["songs.uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("playlist_uuid", "song_uuid", name="uq_playlist_song"),
    )
    op.create_index("ix_playlist_songs_playlist_uuid", "playlist_songs", ["playlist_uuid"])
    op.create_index("ix_playlist_songs_song_uuid", "playlist_songs", ["song_uuid"])


def downgrade() -> None:
    op.drop_table("playlist_songs")
    op.drop_table("playlists")
    op.drop_table("songs")
