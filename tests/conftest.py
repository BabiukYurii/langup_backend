import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import settings
from app.database.postgres import get_session
from app.main import create_app
from app.models.auth import OAuthAccount, RefreshToken
from app.models.exercise import Exercise
from app.models.exercise_attempt import ExerciseAttempt
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.source import Source
from app.models.subscription import Subscription
from app.models.usage_limit import UsageLimit
from app.models.user import User
from app.models.user_word import UserWord
from app.models.webhook_event import WebhookEvent
from app.models.word import Word
from app.models.word_context import WordContext

# Tables the test suite needs (created on the in-memory sqlite engine).
# Order matters for FKs: sources before word_contexts; exercises before attempts.
TEST_TABLES = [
    User.__table__,
    Word.__table__,
    OAuthAccount.__table__,
    RefreshToken.__table__,
    Source.__table__,
    WordContext.__table__,
    UserWord.__table__,
    Exercise.__table__,
    ExerciseAttempt.__table__,
    Plan.__table__,
    Subscription.__table__,
    Payment.__table__,
    WebhookEvent.__table__,
    UsageLimit.__table__,
]


# Background tasks open their OWN session and AI client, so they bypass the
# sqlite override and would hit the real database and the real gateway.
_BACKGROUND_AI_FLAGS = ("EXERCISE_POOL_AUTOFILL", "TRANSLATE_ON_CAPTURE")


@pytest.fixture(autouse=True)
def _disable_background_ai():
    # Force them off no matter what the developer's .env says.
    original = {name: getattr(settings.exercises, name) for name in _BACKGROUND_AI_FLAGS}
    for name in _BACKGROUND_AI_FLAGS:
        setattr(settings.exercises, name, False)
    yield
    for name, value in original.items():
        setattr(settings.exercises, name, value)


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
