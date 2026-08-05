from pydantic import Field

from app.core.config.base import BaseConfig


class AuthConfig(BaseConfig):
    # Used to validate the audience of incoming Google ID tokens.
    GOOGLE_CLIENT_ID: str = Field("", alias="GOOGLE_CLIENT_ID")

    # How long after a refresh token is rotated its replay is still treated as
    # a race rather than as theft.
    #
    # The extension popup, its service worker and every open cabinet tab are
    # separate contexts that cannot coordinate, so two of them refreshing at
    # once is routine — and without this, that ends every session of an
    # innocent user. A thief holding the token can already use it at any
    # earlier moment, so a window this short adds no real exposure.
    REFRESH_REUSE_GRACE_SECONDS: int = 15
