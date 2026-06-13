from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class WebhookEvent(Base, UUIDMixin, TimestampMixin):
    # Inbound provider webhook store; enforces idempotent processing.
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    provider = Column(String(16), nullable=False, index=True)  # PaymentProvider
    event_id = Column(String(255), nullable=False, index=True)  # provider's event id
    event_type = Column(String(128), nullable=True)
    payload = Column(JSONB, nullable=False)  # raw verified payload
    processed_at = Column(DateTime, nullable=True)  # null until handled
    status = Column(String(16), nullable=False, server_default="RECEIVED")  # RECEIVED/PROCESSED/FAILED
    error = Column(Text, nullable=True)
