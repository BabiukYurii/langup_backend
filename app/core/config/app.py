from pydantic import Field

from app.core.config.base import BaseConfig


class AppBaseConfig(BaseConfig):
    APP_NAME: str = Field("LangUp", alias="APP_NAME")
    ENV: str = Field("local", alias="ENV")
    DEBUG: bool = Field(True, alias="DEBUG")
    HOST: str = Field("0.0.0.0", alias="HOST")
    PORT: int = Field(8000, alias="PORT")
    WORKERS: int = Field(1, alias="WORKERS")
    API_PREFIX: str = Field("/api", alias="API_PREFIX")
    BASE_URL: str = Field("http://localhost:8000", alias="BASE_URL")
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOWED_ORIGINS")

    # Identity of the Android build, for App Links. With these set, the site
    # serves /.well-known/assetlinks.json and Android hands our own https URLs
    # straight to the installed app instead of opening a browser tab — which is
    # what lets a finished Stripe checkout land back inside the app.
    #
    # The fingerprint is the SHA-256 of the SIGNING certificate and therefore
    # differs between a debug build, a release key and Play App Signing. List
    # all of them, comma-separated, or App Links silently stop verifying and
    # every return falls back to the browser.
    ANDROID_PACKAGE_NAME: str = Field("com.langup.langup_mobile", alias="ANDROID_PACKAGE_NAME")
    ANDROID_SHA256_FINGERPRINTS: str = Field("", alias="ANDROID_SHA256_FINGERPRINTS")

    # Scheme the bridge page falls back to when App Links are not verified —
    # an older Android, a differently signed build, or iOS later on.
    DEEP_LINK_SCHEME: str = Field("langup", alias="DEEP_LINK_SCHEME")

    @property
    def android_fingerprints(self) -> list[str]:
        return [f.strip().upper() for f in self.ANDROID_SHA256_FINGERPRINTS.split(",") if f.strip()]
