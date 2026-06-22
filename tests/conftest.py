import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.postgres import get_session
from app.main import create_app
from app.models.auth import OAuthAccount
from app.models.user import User
from app.models.word import Word

# Tables the test suite needs (created on the in-memory sqlite engine).
TEST_TABLES = [User.__table__, Word.__table__, OAuthAccount.__table__]


@pytest_asyncio.fixture
async def engine():
    # In-memory sqlite shared across the test via a single pooled connection.
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        for table in TEST_TABLES:
            await conn.run_sync(table.create)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(sessionmaker) -> AsyncSession:
    async with sessionmaker() as s:
        yield s


@pytest_asyncio.fixture
async def app(sessionmaker):
    async def _override_session():
        async with sessionmaker() as s:
            yield s

    application = create_app()
    application.dependency_overrides[get_session] = _override_session
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
