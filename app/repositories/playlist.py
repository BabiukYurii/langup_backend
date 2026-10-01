from uuid import UUID

from sqlalchemy import func, select

from app.models import Playlist, PlaylistSong, Song
from app.repositories.base import BaseRepository


class SongRepository(BaseRepository[Song]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Song)

    async def get_by_match_key(self, match_key: str) -> Song | None:
        return await self.get_one(match_key=match_key)


class PlaylistRepository(BaseRepository[Playlist]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Playlist)

    async def list_for_user(self, user_id: int) -> list[Playlist]:
        stmt = select(Playlist).where(Playlist.user_id == user_id).order_by(Playlist.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_for_user(self, user_id: int, uuid: UUID) -> Playlist | None:
        return await self.get_one(uuid=uuid, user_id=user_id)


class PlaylistSongRepository(BaseRepository[PlaylistSong]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=PlaylistSong)

    async def count_for_playlist(self, playlist_uuid: UUID) -> int:
        stmt = select(func.count()).select_from(PlaylistSong).where(PlaylistSong.playlist_uuid == playlist_uuid)
        return (await self.session.execute(stmt)).scalar() or 0

    async def max_priority(self, playlist_uuid: UUID) -> int:
        """Highest warming priority in this playlist, 0 when it has none.

        An ordinal counter rather than a timestamp: two tracks pasted in the
        same second have to come out in the order they were pasted, and seconds
        cannot express that.
        """
        stmt = select(func.coalesce(func.max(PlaylistSong.priority), 0)).where(
            PlaylistSong.playlist_uuid == playlist_uuid
        )
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def songs_for_playlist(self, playlist_uuid: UUID) -> list[tuple[PlaylistSong, Song]]:
        """Ordered (link, song) pairs for a playlist."""
        stmt = (
            select(PlaylistSong, Song)
            .join(Song, PlaylistSong.song_uuid == Song.uuid)
            .where(PlaylistSong.playlist_uuid == playlist_uuid)
            .order_by(PlaylistSong.position)
        )
        return [(link, song) for link, song in (await self.session.execute(stmt)).all()]
