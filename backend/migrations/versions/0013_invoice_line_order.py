"""Allow temporary line numbers while reordering drafts."""

from alembic import op


revision = "0013_invoice_line_order"
down_revision = "0012_invoice_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_invoice_items_line", "invoice_items", type_="check")
    op.create_check_constraint("ck_invoice_items_line", "invoice_items", "line_number > 0")


def downgrade():
    op.drop_constraint("ck_invoice_items_line", "invoice_items", type_="check")
    op.create_check_constraint("ck_invoice_items_line", "invoice_items", "line_number BETWEEN 1 AND 100")
