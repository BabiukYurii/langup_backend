from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)  # login identity
    hashed_password = Column(String(255), nullable=True)  # null for OAuth-only accounts
    full_name = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False, server_default="USER", index=True)  # RoleEnum
    status = Column(String(32), nullable=False, server_default="ACTIVE")  # UserStatus
    is_email_verified = Column(Boolean, nullable=False, server_default="false")
    is_2fa_enabled = Column(Boolean, nullable=False, server_default="false")
    native_language = Column(String(8), nullable=True)  # LanguageCode the user speaks
    target_language = Column(String(8), nullable=True)  # language being learned
    preferences = Column(JSONB, nullable=True)  # UI/learning preferences blob
    last_login_at = Column(DateTime, nullable=True)

    # relationships
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    words = relationship("UserWord", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False)
