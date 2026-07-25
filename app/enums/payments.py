from app.enums.base import BaseStrEnum


class PlanTier(BaseStrEnum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"


class BillingInterval(BaseStrEnum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class PaymentProvider(BaseStrEnum):
    STRIPE = "STRIPE"
    PAYPAL = "PAYPAL"
    GOOGLE_PAY = "GOOGLE_PAY"
    BLIK = "BLIK"


class SubscriptionStatus(BaseStrEnum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class PaymentStatus(BaseStrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# Subscription statuses that grant access to paid features.
ACTIVE_SUBSCRIPTION_STATUSES = (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE)
