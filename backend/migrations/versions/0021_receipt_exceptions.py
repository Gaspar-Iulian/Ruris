"""Add pending receipt clarifications and acceptance splits."""

from alembic import op
import sqlalchemy as sa

revision = "0021_receipt_exceptions"
down_revision = "0020_invoice_order_source"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("receipt_items", "product_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("receipt_items", sa.Column("resolved_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"))
    for column, target in (("origin_item_id", "receipt_items"), ("pending_order_item_id", "purchase_order_items")):
        op.add_column("receipt_items", sa.Column(column, sa.BigInteger(), nullable=True))
        op.create_foreign_key(f"fk_receipt_items_{column}", "receipt_items", target, [column], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_receipt_items_{column}", "receipt_items", [column])
    op.drop_constraint("ck_receipt_items_balance", "receipt_items", type_="check")
    op.create_check_constraint("ck_receipt_items_balance", "receipt_items",
                               "received_quantity = accepted_quantity + rejected_quantity + pending_quantity + resolved_quantity")
    op.create_check_constraint("ck_receipt_items_resolved", "receipt_items",
                               "resolved_quantity >= 0 AND resolved_quantity <> 'NaN'::numeric")
    op.create_check_constraint("ck_receipt_items_acceptance", "receipt_items",
                               "origin_item_id IS NULL OR (origin_item_id <> id AND product_id IS NOT NULL "
                               "AND purchase_order_item_id IS NOT NULL AND pending_order_item_id IS NULL "
                               "AND accepted_quantity = received_quantity AND rejected_quantity = 0 "
                               "AND pending_quantity = 0 AND resolved_quantity = 0)")


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM receipt_items WHERE origin_item_id IS NOT NULL OR product_id IS NULL OR pending_order_item_id IS NOT NULL)")):
        raise RuntimeError("Receipt exceptions must be retained; downgrade would lose their history.")
    op.drop_constraint("ck_receipt_items_acceptance", "receipt_items", type_="check")
    op.drop_constraint("ck_receipt_items_resolved", "receipt_items", type_="check")
    op.drop_constraint("ck_receipt_items_balance", "receipt_items", type_="check")
    op.create_check_constraint("ck_receipt_items_balance", "receipt_items",
                               "received_quantity = accepted_quantity + rejected_quantity + pending_quantity")
    for column in ("pending_order_item_id", "origin_item_id"):
        op.drop_index(f"ix_receipt_items_{column}", table_name="receipt_items")
        op.drop_constraint(f"fk_receipt_items_{column}", "receipt_items", type_="foreignkey")
        op.drop_column("receipt_items", column)
    op.drop_column("receipt_items", "resolved_quantity")
    op.alter_column("receipt_items", "product_id", existing_type=sa.BigInteger(), nullable=False)
