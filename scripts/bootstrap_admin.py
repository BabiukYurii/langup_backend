#!/usr/bin/env python3
"""Make sure the instance has an administrator.

Only a SUPER_ADMIN may create a privileged user, so a fresh database — or one
that has just been emptied — leaves nobody able to reach the admin panel and no
way in short of hand-written SQL. This closes that gap.

Run from entrypoint.sh on every container start, deliberately not as a
migration: a migration is stamped in `alembic_version` and never runs again, so
it cannot help the second time a database is emptied, which is the case that
matters. Here the work is behind an "is there already an admin" check instead,
so every start but the one that needs it is a no-op.

Silent and harmless when ADMIN_BOOTSTRAP_EMAIL/PASSWORD are unset, and it never
fails the start: an instance that cannot seed an admin should still serve the
learners it already has.

    uv run python -m scripts.bootstrap_admin
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bootstrap_admin")


async def ensure_admin() -> str:
    """Create or promote the configured administrator. Returns what happened."""
    from app.core import settings
    from app.core.security.password import hash_password
    from app.core.security.rbac import ADMIN_ROLES
    from app.database.postgres import async_session
    from app.enums.user import RoleEnum, UserStatus
    from app.repositories.user import UserRepository

    email = (settings.auth.ADMIN_BOOTSTRAP_EMAIL or "").strip().lower()
    password = settings.auth.ADMIN_BOOTSTRAP_PASSWORD
    if not email or not password:
        return "not configured"

    roles = tuple(role.value for role in ADMIN_ROLES)
    async with async_session() as session:
        users = UserRepository(session)
        if await users.any_with_role(roles):
            return "an admin already exists"

        existing = await users.get_by_email(email)
        if existing:
            # Registered before the variable was set, or before a wipe put the
            # role back to USER. Promoting beats refusing to act.
            await users.update_one(existing, {"role": RoleEnum.SUPER_ADMIN.value})
            return f"promoted {email} to SUPER_ADMIN"

        await users.create_one(
            {
                "email": email,
                "hashed_password": hash_password(password),
                "role": RoleEnum.SUPER_ADMIN.value,
                "status": UserStatus.ACTIVE.value,
                # Marked verified: there is no inbox to confirm from during a
                # deploy, and saving words is gated on a confirmed address.
                "is_email_verified": True,
            }
        )
        return f"created {email} as SUPER_ADMIN"


def main() -> int:
    try:
        logger.info("bootstrap_admin: %s", asyncio.run(ensure_admin()))
    except Exception:  # noqa: BLE001 — seeding must never stop the app starting
        logger.exception("bootstrap_admin: failed, carrying on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
