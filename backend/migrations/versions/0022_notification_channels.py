"""Allow receipt reminders and configurable SMTP delivery."""

from alembic import op
import sqlalchemy as sa

revision = "0022_notification_channels"
down_revision = "0021_receipt_exceptions"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_email_outbox_kind", "email_outbox", type_="check")
    op.drop_constraint("ck_email_outbox_transport", "email_outbox", type_="check")
    op.create_check_constraint("ck_email_outbox_kind", "email_outbox",
                               "kind IN ('OVERDUE', 'BLOCKED_INVOICES', 'RECEIPT_BUYER', 'RECEIPT_WAREHOUSE')")
    op.create_check_constraint("ck_email_outbox_transport", "email_outbox", "transport IN ('LOCAL_MAILPIT', 'SMTP')")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM email_outbox WHERE transport = 'SMTP' OR kind IN ('RECEIPT_BUYER', 'RECEIPT_WAREHOUSE'))")):
        raise RuntimeError("Notification history must be retained before downgrade.")
    op.drop_constraint("ck_email_outbox_kind", "email_outbox", type_="check")
    op.drop_constraint("ck_email_outbox_transport", "email_outbox", type_="check")
    op.create_check_constraint("ck_email_outbox_kind", "email_outbox", "kind IN ('OVERDUE', 'BLOCKED_INVOICES')")
    op.create_check_constraint("ck_email_outbox_transport", "email_outbox", "transport = 'LOCAL_MAILPIT'")
