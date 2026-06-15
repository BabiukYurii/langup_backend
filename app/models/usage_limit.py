from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.models.base import Base, TimestampMixin, UUIDMixin


class UsageLimit(Base, UUIDMixin, TimestampMixin):
    # Per-user, per-period usage counters checked against plan limits.
    __tablename__ = "usage_limits"
    __table_args__ = (UniqueConstraint("user_id", "metric", "period", name="uq_usage_user_metric_period"),)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    metric = Column(String(64), nullable=False)  # e.g. captures, ai_calls
    period = Column(String(16), nullable=False)  # e.g. 2026-06 or 2026-06-14
    used = Column(Integer, nullable=False, server_default="0")
    limit = Column(Integer, nullable=True)  # snapshot of plan limit for the period
