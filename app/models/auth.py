from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


# Authentication-related tables: refresh tokens, sessions/devices, oauth links,
# email-verification & password-reset tokens, and 2FA secrets.


class RefreshToken(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "refresh_tokens"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String(255), unique=True, index=True, nullable=False)  # hashed, never store raw
    session_uuid = Column(UUID(as_uuid=True), ForeignKey("user_sessions.uuid", ondelete="CASCADE"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)  # set on logout / rotation
    replaced_by = Column(UUID(as_uuid=True), nullable=True)  # rotation chain


class UserSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_sessions"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_type = Column(String(32), nullable=True)  # DeviceType (browser/extension/mobile)
    device_name = Column(String(255), nullable=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    is_trusted = Column(Boolean, nullable=False, server_default="false")
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")


class OAuthAccount(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id", name="uq_oauth_provider_account"),)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String(32), nullable=False)  # OAuthProvider (GOOGLE)
    provider_account_id = Column(String(255), nullable=False)  # subject id from provider
    email = Column(String(255), nullable=True)

    user = relationship("User", back_populates="oauth_accounts")


class EmailVerificationToken(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "email_verification_tokens"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class TwoFactorSecret(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "two_factor_secrets"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    method = Column(String(16), nullable=False, server_default="TOTP")  # TwoFactorMethod
    secret_encrypted = Column(Text, nullable=False)  # encrypted TOTP seed
    backup_codes = Column(JSONB, nullable=True)  # hashed one-time recovery codes
    confirmed_at = Column(DateTime, nullable=True)
