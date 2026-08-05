from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.models.base import Base, TimestampMixin, UUIDMixin, UUIDType


class Payment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payments"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    subscription_uuid = Column(UUIDType, ForeignKey("subscriptions.uuid", ondelete="SET NULL"), nullable=True)
    provider = Column(String(16), nullable=False)  # PaymentProvider
    provider_payment_id = Column(String(255), nullable=True, index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, server_default="USD")
    status = Column(String(16), nullable=False)  # PaymentStatus
    idempotency_key = Column(String(255), unique=True, nullable=True)  # safe retries
    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, server_default="0")
