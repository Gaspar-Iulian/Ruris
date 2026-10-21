"""Keep supplier totals separate from calculated totals."""

from alembic import op
import sqlalchemy as sa

revision = "0023_invoice_declared_totals"
down_revision = "0022_notification_channels"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("declared_net_amount", "declared_vat_amount", "declared_total_amount"):
        op.add_column("invoices", sa.Column(name, sa.Numeric(18, 2), nullable=True))
    op.create_check_constraint("ck_invoices_declared_amounts", "invoices",
        "(declared_net_amount IS NULL AND declared_vat_amount IS NULL AND declared_total_amount IS NULL) OR "
        "(declared_net_amount IS NOT NULL AND declared_vat_amount IS NOT NULL AND declared_total_amount IS NOT NULL "
        "AND declared_net_amount >= 0 AND declared_net_amount < 'NaN'::numeric "
        "AND declared_vat_amount >= 0 AND declared_vat_amount < 'NaN'::numeric "
        "AND declared_total_amount >= 0 AND declared_total_amount < 'NaN'::numeric)")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM invoices WHERE declared_total_amount IS NOT NULL)")):
        raise RuntimeError("Supplier totals must be retained before downgrade.")
    op.drop_constraint("ck_invoices_declared_amounts", "invoices", type_="check")
    for name in ("declared_total_amount", "declared_vat_amount", "declared_net_amount"):
        op.drop_column("invoices", name)
