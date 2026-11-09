from pydantic import Field

from app.core.config.base import BaseConfig


class AuthConfig(BaseConfig):
    # Used to validate the audience of incoming Google ID tokens.
    GOOGLE_CLIENT_ID: str = Field("", alias="GOOGLE_CLIENT_ID")

    # The first administrator of an instance that has none.
    #
    # Only a SUPER_ADMIN may create a privileged user, which leaves a fresh or
    # emptied database with nobody able to reach the admin panel and no way in
    # short of hand-written SQL. These two give a way in.
    #
    # Checked on every container start rather than once in a migration: a
    # migration is stamped in alembic_version and never runs again, so it
    # cannot help the second time a database is emptied — which is exactly
    # when this is needed.
    #
    # Bound to one address on purpose. "The first account to register becomes
    # an admin" is simpler and hands the keys to whoever shows up first the
    # next time the table is empty.
    ADMIN_BOOTSTRAP_EMAIL: str = Field("", alias="ADMIN_BOOTSTRAP_EMAIL")
    ADMIN_BOOTSTRAP_PASSWORD: str = Field("", alias="ADMIN_BOOTSTRAP_PASSWORD")

    # How long after a refresh token is rotated its replay is still treated as
    # a race rather than as theft.
    #
    # The extension popup, its service worker and every open cabinet tab are
    # separate contexts that cannot coordinate, so two of them refreshing at
    # once is routine — and without this, that ends every session of an
    # innocent user. A thief holding the token can already use it at any
    # earlier moment, so a window this short adds no real exposure.
    REFRESH_REUSE_GRACE_SECONDS: int = 15
