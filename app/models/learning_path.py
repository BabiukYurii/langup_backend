from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class LearningPath(Base, UUIDMixin, TimestampMixin):
    # AI-generated personalized study plan (ordered milestones).
    __tablename__ = "learning_paths"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(255), nullable=True)
    goal = Column(Text, nullable=True)  # user goal the path optimizes for
    steps = Column(JSONB, nullable=False)  # ordered milestones with target words/skills
    is_active = Column(Boolean, nullable=False, server_default="true")
    generated_by = Column(UUID(as_uuid=True), ForeignKey("ai_generations.uuid", ondelete="SET NULL"), nullable=True)
