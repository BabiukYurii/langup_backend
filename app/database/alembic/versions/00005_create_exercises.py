"""create exercises, exercise_attempts

Revision ID: 00005
Revises: 00004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00005"
down_revision = "00004"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word_uuid", _UUID, nullable=True),
        sa.Column("context_uuid", _UUID, nullable=True),
        sa.Column("exercise_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="READY", nullable=False),
        sa.Column("difficulty", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("answer", postgresql.JSONB(), nullable=False),
        sa.Column("is_ai_generated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("generation_uuid", _UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_uuid"], ["words.uuid"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["context_uuid"], ["word_contexts.uuid"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index("ix_exercises_user_id", "exercises", ["user_id"])
    op.create_index("ix_exercises_exercise_type", "exercises", ["exercise_type"])
    op.create_index("ix_exercises_status", "exercises", ["status"])
    op.create_index("ix_exercises_created_at", "exercises", ["created_at"])
    # Hot path: GET /exercises/next pulls the oldest READY item for a user.
    op.create_index("ix_exercises_user_status", "exercises", ["user_id", "status"])

    op.create_table(
        "exercise_attempts",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exercise_uuid", _UUID, nullable=False),
        sa.Column("session_uuid", _UUID, nullable=True),
        sa.Column("submitted_answer", postgresql.JSONB(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("quality", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_uuid"], ["exercises.uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index("ix_exercise_attempts_user_id", "exercise_attempts", ["user_id"])
    op.create_index("ix_exercise_attempts_exercise_uuid", "exercise_attempts", ["exercise_uuid"])
    op.create_index("ix_exercise_attempts_created_at", "exercise_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_table("exercise_attempts")
    op.drop_table("exercises")
