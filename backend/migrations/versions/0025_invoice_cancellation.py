"""Add retained invoice cancellation."""

from alembic import op
import sqlalchemy as sa

revision = "0025_invoice_cancellation"
down_revision = "0024_document_attachments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("cancelled_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_invoices_cancelled_by")))
    op.add_column("invoices", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("cancellation_reason", sa.String(1000)))
    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.create_check_constraint("ck_invoices_status", "invoices", "status IN ('DRAFT', 'BLOCKED', 'VERIFIED', 'APPROVED', 'PAID', 'CANCELLED')")
    op.create_check_constraint("ck_invoices_cancellation", "invoices",
        "(status = 'CANCELLED' AND cancelled_by_id IS NOT NULL AND cancelled_at IS NOT NULL "
        "AND cancellation_reason IS NOT NULL AND length(btrim(cancellation_reason)) BETWEEN 1 AND 1000) OR "
        "(status <> 'CANCELLED' AND cancelled_by_id IS NULL AND cancelled_at IS NULL AND cancellation_reason IS NULL)")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM invoices WHERE status = 'CANCELLED')")):
        raise RuntimeError("Cancelled invoice history must be retained before downgrade.")
    op.drop_constraint("ck_invoices_cancellation", "invoices", type_="check")
    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.create_check_constraint("ck_invoices_status", "invoices", "status IN ('DRAFT', 'BLOCKED', 'VERIFIED', 'APPROVED', 'PAID')")
    op.drop_column("invoices", "cancellation_reason")
    op.drop_column("invoices", "cancelled_at")
    op.drop_column("invoices", "cancelled_by_id")
