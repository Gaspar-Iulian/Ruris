"""Persist email retry times."""

from alembic import op
import sqlalchemy as sa


revision = "0011_email_retry_schedule"
down_revision = "0010_email_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("email_outbox", "next_attempt_at")
