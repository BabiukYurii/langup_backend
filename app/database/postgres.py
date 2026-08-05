# Async SQLAlchemy engine + session factory.
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import settings

engine = create_async_engine(
    settings.db.url,
    echo=settings.db.ECHO,
    future=True,
    connect_args=settings.db.connect_args,
    # Neon (serverless) closes idle connections; verify liveness before use and
    # recycle connections before they can go stale — avoids "connection is closed".
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
