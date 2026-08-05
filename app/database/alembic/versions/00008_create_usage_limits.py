"""create usage_limits

Revision ID: 00008
Revises: 00007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00008"
down_revision = "00007"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "usage_limits",
        sa.Column("uuid", _UUID, server_default=_GEN, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("user_id", "metric", "period", name="uq_usage_user_metric_period"),
    )
    op.create_index("ix_usage_limits_user_id", "usage_limits", ["user_id"])


def downgrade() -> None:
    op.drop_table("usage_limits")
