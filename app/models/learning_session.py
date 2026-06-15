from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)

from app.models.base import Base, TimestampMixin, UUIDMixin


class LearningSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "learning_sessions"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    mode = Column(String(32), nullable=True)  # review / new / quiz / timed
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, server_default="0")
    correct_items = Column(Integer, nullable=False, server_default="0")
    xp_earned = Column(Integer, nullable=False, server_default="0")
