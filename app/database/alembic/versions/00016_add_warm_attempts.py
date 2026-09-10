"""add fruitless_attempts to song_warm_states

Revision ID: 00016
Revises: 00015
"""

import sqlalchemy as sa
from alembic import op

revision = "00016"
down_revision = "00015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "song_warm_states",
        sa.Column("fruitless_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    # Existing rows start from zero on purpose: the pairs that were stuck have
    # earned a fresh set of tries under the new rule, and the ones that finished
    # are excluded by completed_at anyway.


def downgrade() -> None:
    op.drop_column("song_warm_states", "fruitless_attempts")
