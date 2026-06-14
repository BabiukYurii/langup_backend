# Import every model so Alembic autogenerate and relationships resolve.
from app.models.base import Base
from app.models.user import User
from app.models.auth import (
    EmailVerificationToken,
    OAuthAccount,
    PasswordResetToken,
    RefreshToken,
    TwoFactorSecret,
    UserSession,
)
from app.models.audit_log import AuditLog
from app.models.word import Word
from app.models.source import Source
from app.models.word_context import WordContext
from app.models.user_word import UserWord
from app.models.exercise import Exercise
from app.models.exercise_attempt import ExerciseAttempt
from app.models.learning_session import LearningSession
from app.models.learning_path import LearningPath
from app.models.review_schedule import ReviewSchedule
from app.models.ai_generation import AIGeneration
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.invoice import Invoice
from app.models.promo_code import PromoCode
from app.models.webhook_event import WebhookEvent
from app.models.usage_limit import UsageLimit

__all__ = [
    "Base", "User", "RefreshToken", "UserSession", "OAuthAccount",
    "EmailVerificationToken", "PasswordResetToken", "TwoFactorSecret", "AuditLog",
    "Word", "Source", "WordContext", "UserWord", "Exercise", "ExerciseAttempt",
    "LearningSession", "LearningPath", "ReviewSchedule", "AIGeneration",
    "Plan", "Subscription", "Payment", "Invoice", "PromoCode",
    "WebhookEvent", "UsageLimit",
]
