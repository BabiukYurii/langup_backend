from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Subscription(Base, UUIDMixin, TimestampMixin):
    # A user's current subscription; state evolves via the state machine.
    __tablename__ = "subscriptions"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    plan_uuid = Column(UUID(as_uuid=True), ForeignKey("plans.uuid", ondelete="RESTRICT"), nullable=False)
    provider = Column(String(16), nullable=True)  # PaymentProvider
    provider_subscription_id = Column(String(255), nullable=True, index=True)
    status = Column(String(16), nullable=False, server_default="TRIALING")  # SubscriptionStatus
    trial_end_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, server_default="false")
    canceled_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="subscription")
