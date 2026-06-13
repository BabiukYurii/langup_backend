from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Invoice(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "invoices"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    subscription_uuid = Column(UUID(as_uuid=True), ForeignKey("subscriptions.uuid", ondelete="SET NULL"), nullable=True)
    payment_uuid = Column(UUID(as_uuid=True), ForeignKey("payments.uuid", ondelete="SET NULL"), nullable=True)
    number = Column(String(64), unique=True, nullable=False, index=True)  # human-facing invoice no.
    status = Column(String(16), nullable=False)  # InvoiceStatus (DRAFT/OPEN/PAID/VOID)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, server_default="USD")
    line_items = Column(JSONB, nullable=True)
    pdf_key = Column(Text, nullable=True)  # object-storage key for rendered PDF
    issued_at = Column(DateTime, nullable=True)
