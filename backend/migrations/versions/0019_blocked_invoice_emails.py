"""Allow daily blocked invoice digests."""

from alembic import op


revision = "0019_blocked_invoice_emails"
down_revision = "0018_invoice_payment"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_email_outbox_kind", "email_outbox", type_="check")
    op.create_check_constraint("ck_email_outbox_kind", "email_outbox", "kind IN ('OVERDUE', 'BLOCKED_INVOICES')")


def downgrade():
    op.drop_constraint("ck_email_outbox_kind", "email_outbox", type_="check")
    op.create_check_constraint("ck_email_outbox_kind", "email_outbox", "kind = 'OVERDUE'")
