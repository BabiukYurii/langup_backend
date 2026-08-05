from pydantic import Field

from app.core.config.base import BaseConfig


class PaymentsConfig(BaseConfig):
    # Stripe is the first (and currently only) live provider.
    STRIPE_API_KEY: str = Field("", alias="STRIPE_API_KEY")
    STRIPE_WEBHOOK_SECRET: str = Field("", alias="STRIPE_WEBHOOK_SECRET")
    CURRENCY: str = Field("USD", alias="PAYMENTS_CURRENCY")
    TRIAL_DAYS: int = Field(7, alias="PAYMENTS_TRIAL_DAYS")
    # Where Stripe Checkout sends the customer back. Relative paths are joined
    # onto BASE_URL by the billing service.
    SUCCESS_PATH: str = Field("/app/index.html?checkout=success", alias="PAYMENTS_SUCCESS_PATH")
    CANCEL_PATH: str = Field("/app/index.html?checkout=cancel", alias="PAYMENTS_CANCEL_PATH")

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_API_KEY)
