from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Plan(Base, UUIDMixin, TimestampMixin):
    # Subscription plan catalog entry.
    __tablename__ = "plans"

    code = Column(String(64), unique=True, nullable=False, index=True)  # e.g. premium_monthly
    tier = Column(String(16), nullable=False)  # PlanTier (FREE/PREMIUM)
    interval = Column(String(16), nullable=True)  # BillingInterval (MONTHLY/YEARLY)
    price_cents = Column(Integer, nullable=False, server_default="0")
    currency = Column(String(8), nullable=False, server_default="USD")
    trial_days = Column(Integer, nullable=False, server_default="0")
    limits = Column(JSONB, nullable=True)  # usage limits (captures/day, ai_calls/month, ...)
    provider_price_ids = Column(JSONB, nullable=True)  # map provider -> external price id
    is_active = Column(Boolean, nullable=False, server_default="true")
