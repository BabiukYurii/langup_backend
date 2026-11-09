"""An instance that has no administrator can still get one.

Only a SUPER_ADMIN may create a privileged user, so a fresh database — or one
just emptied — has nobody able to reach the admin panel and no way in short of
hand-written SQL. This runs on every container start and closes that gap
exactly once.

Not a migration, and that is the point: a migration is stamped in
alembic_version and never runs again, so it could not help the second time a
database is emptied.
"""

import pytest

from app.core import settings
from app.core.security.password import verify_password
from app.enums.user import RoleEnum
from app.repositories.user import UserRepository
from scripts.bootstrap_admin import ensure_admin

EMAIL = "boss@langup.app"
PASSWORD = "a-long-enough-secret"


@pytest.fixture
def configured(monkeypatch, sessionmaker):
    """Point the seeder at the test database and give it credentials."""
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_EMAIL", EMAIL)
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setattr("app.database.postgres.async_session", sessionmaker)


@pytest.fixture
def unconfigured(monkeypatch, sessionmaker):
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_EMAIL", "")
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_PASSWORD", "")
    monkeypatch.setattr("app.database.postgres.async_session", sessionmaker)


async def test_nothing_configured_does_nothing(unconfigured, sessionmaker):
    assert await ensure_admin() == "not configured"
    async with sessionmaker() as session:
        assert await UserRepository(session).get_by_email(EMAIL) is None


async def test_an_empty_instance_gets_its_first_admin(configured, sessionmaker):
    result = await ensure_admin()

    assert "created" in result
    async with sessionmaker() as session:
        user = await UserRepository(session).get_by_email(EMAIL)
        assert user is not None
        assert user.role == RoleEnum.SUPER_ADMIN.value
        # Saving words is gated on a confirmed address, and a deploy has no
        # inbox to confirm from.
        assert user.is_email_verified is True


async def test_the_password_from_the_environment_actually_works(configured, sessionmaker):
    await ensure_admin()
    async with sessionmaker() as session:
        user = await UserRepository(session).get_by_email(EMAIL)
        assert verify_password(PASSWORD, user.hashed_password)
        assert not verify_password("something else", user.hashed_password)


async def test_running_again_changes_nothing(configured, sessionmaker):
    """It runs on every container start, so this is the normal case."""
    await ensure_admin()
    assert await ensure_admin() == "an admin already exists"

    async with sessionmaker() as session:
        found, total = await UserRepository(session).search(limit=50)
        assert total == 1


async def test_an_existing_admin_is_left_alone(configured, sessionmaker):
    """Somebody else already holds the keys; the seed must not add a second."""
    from app.models import User

    async with sessionmaker() as session:
        session.add(User(email="other@x.io", role=RoleEnum.ADMIN.value))
        await session.commit()

    assert await ensure_admin() == "an admin already exists"
    async with sessionmaker() as session:
        assert await UserRepository(session).get_by_email(EMAIL) is None


async def test_an_account_that_already_registered_is_promoted(configured, sessionmaker):
    """Registered before the variable was set — promoting beats refusing."""
    from app.models import User

    async with sessionmaker() as session:
        session.add(User(email=EMAIL, role=RoleEnum.USER.value))
        await session.commit()

    assert "promoted" in await ensure_admin()
    async with sessionmaker() as session:
        user = await UserRepository(session).get_by_email(EMAIL)
        assert user.role == RoleEnum.SUPER_ADMIN.value


async def test_the_seeded_admin_can_use_the_admin_panel(configured, client):
    """End to end: the point is a working way in, not a row in a table."""
    await ensure_admin()

    login = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get("/api/admin/users", headers=headers)).status_code == 200
