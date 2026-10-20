"""Add durable local email delivery records."""

from alembic import op
import sqlalchemy as sa


revision = "0010_email_delivery"
down_revision = "0009_stock_movements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("transport", sa.String(20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recipient_email", sa.String(254), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(80), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("kind", "transport", "as_of", "recipient_user_id", name="uq_email_outbox_daily"),
        sa.CheckConstraint("kind = 'OVERDUE'", name="ck_email_outbox_kind"),
        sa.CheckConstraint("transport = 'LOCAL_MAILPIT'", name="ck_email_outbox_transport"),
        sa.CheckConstraint("status IN ('PENDING', 'SENDING', 'SENT', 'FAILED', 'UNKNOWN', 'SKIPPED')", name="ck_email_outbox_status"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= 3", name="ck_email_outbox_attempts"),
    )
    op.create_index("ix_email_outbox_status", "email_outbox", ["status"])
    op.create_table(
        "email_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("outbox_id", sa.BigInteger(), sa.ForeignKey("email_outbox.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("outbox_id", "attempt_number", name="uq_email_attempts_number"),
        sa.CheckConstraint("attempt_number BETWEEN 1 AND 3", name="ck_email_attempts_number"),
        sa.CheckConstraint("status IN ('SENDING', 'SENT', 'FAILED', 'UNKNOWN')", name="ck_email_attempts_status"),
    )
    op.create_index("ix_email_attempts_outbox_id", "email_attempts", ["outbox_id"])


def downgrade():
    op.drop_table("email_attempts")
    op.drop_table("email_outbox")
