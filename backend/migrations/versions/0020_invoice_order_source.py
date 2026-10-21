"""Link invoice lines to purchase order lines."""

from alembic import op
import sqlalchemy as sa

revision = "0020_invoice_order_source"
down_revision = "0019_blocked_invoice_emails"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoice_items", sa.Column("purchase_order_item_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_invoice_items_order_item", "invoice_items", "purchase_order_items",
                          ["purchase_order_item_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_invoice_items_purchase_order_item_id", "invoice_items", ["purchase_order_item_id"])


def downgrade():
    op.drop_index("ix_invoice_items_purchase_order_item_id", table_name="invoice_items")
    op.drop_constraint("fk_invoice_items_order_item", "invoice_items", type_="foreignkey")
    op.drop_column("invoice_items", "purchase_order_item_id")
