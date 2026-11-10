from pydantic import Field

from app.core.config.base import BaseConfig


class PaymentsConfig(BaseConfig):
    # Stripe is the first (and currently only) live provider.
    STRIPE_API_KEY: str = Field("", alias="STRIPE_API_KEY")
    STRIPE_WEBHOOK_SECRET: str = Field("", alias="STRIPE_WEBHOOK_SECRET")
    CURRENCY: str = Field("USD", alias="PAYMENTS_CURRENCY")
    TRIAL_DAYS: int = Field(7, alias="PAYMENTS_TRIAL_DAYS")
    # How long a paid period keeps granting access after it ends.
    #
    # A row says ACTIVE until a renewal webhook moves the period forward, so a
    # webhook that is late — Stripe retries, networks fail — would otherwise cut
    # a paying customer off mid-session. A few days of unpaid access is the far
    # cheaper mistake. Set to 0 to expire the moment the period ends.
    GRACE_DAYS: int = Field(3, alias="PAYMENTS_GRACE_DAYS")
    # The subscription plan an instance offers, seeded when it has none.
    #
    # Plans are configuration, not user data, so an emptied database loses them
    # and checkout stops working with nothing in the UI to explain why. Seeded
    # from entrypoint.sh on every start, and a no-op once a plan exists.
    #
    # Nothing is seeded without a price id: a plan row without one looks
    # configured and then fails at checkout, which is worse than no plan at
    # all. The id is not a secret — Stripe price ids are used client-side — but
    # it differs between test and live, so it belongs in .env rather than here.
    PLAN_BOOTSTRAP_STRIPE_PRICE_ID: str = Field("", alias="PLAN_BOOTSTRAP_STRIPE_PRICE_ID")
    PLAN_BOOTSTRAP_CODE: str = Field("premium_monthly", alias="PLAN_BOOTSTRAP_CODE")
    PLAN_BOOTSTRAP_PRICE_CENTS: int = Field(1999, alias="PLAN_BOOTSTRAP_PRICE_CENTS")
    PLAN_BOOTSTRAP_CURRENCY: str = Field("PLN", alias="PLAN_BOOTSTRAP_CURRENCY")
    PLAN_BOOTSTRAP_TRIAL_DAYS: int = Field(0, alias="PLAN_BOOTSTRAP_TRIAL_DAYS")

    # Where Stripe Checkout sends the customer back. Relative paths are joined
    # onto BASE_URL by the billing service.
    SUCCESS_PATH: str = Field("/app/index.html?checkout=success", alias="PAYMENTS_SUCCESS_PATH")
    CANCEL_PATH: str = Field("/app/index.html?checkout=cancel", alias="PAYMENTS_CANCEL_PATH")

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_API_KEY)
