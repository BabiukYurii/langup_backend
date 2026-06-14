from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class PromoCode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "promo_codes"

    code = Column(String(64), unique=True, nullable=False, index=True)
    type = Column(String(16), nullable=False)  # PromoCodeType (PERCENT/FIXED/TRIAL)
    value = Column(Numeric(8, 2), nullable=False)  # percent or fixed amount
    currency = Column(String(8), nullable=True)
    max_redemptions = Column(Integer, nullable=True)
    times_redeemed = Column(Integer, nullable=False, server_default="0")
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
