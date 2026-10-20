"""Add receipt drafts."""

from alembic import op
import sqlalchemy as sa


revision = "0008_receipts"
down_revision = "0007_purchase_orders"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "receipts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("number", sa.String(40), sa.Computed("'REC-' || id::text", persisted=True), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("delivery_reference", sa.String(120), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), server_default="DRAFT", nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("confirmed_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("number", name="uq_receipts_number"),
        sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')", name="ck_receipts_status"),
        sa.CheckConstraint("version > 0", name="ck_receipts_version"),
        sa.CheckConstraint("char_length(btrim(delivery_reference)) > 0", name="ck_receipts_reference"),
    )
    op.create_index("ix_receipts_supplier_id", "receipts", ["supplier_id"])
    op.create_table(
        "receipt_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("receipt_id", sa.BigInteger(), sa.ForeignKey("receipts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_item_id", sa.BigInteger(), sa.ForeignKey("purchase_order_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 3), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_quantity", sa.Numeric(18, 3), server_default=sa.text("0"), nullable=False),
        sa.Column("pending_quantity", sa.Numeric(18, 3), nullable=False),
        sa.UniqueConstraint("receipt_id", "line_number", name="uq_receipt_items_line"),
        sa.CheckConstraint("line_number > 0", name="ck_receipt_items_line"),
        sa.CheckConstraint("char_length(btrim(description)) > 0", name="ck_receipt_items_description"),
        sa.CheckConstraint("unit IN ('BUC', 'KG', 'L', 'M', 'M2', 'M3')", name="ck_receipt_items_unit"),
        sa.CheckConstraint("received_quantity > 0 AND received_quantity <> 'NaN'::numeric", name="ck_receipt_items_received"),
        sa.CheckConstraint("accepted_quantity >= 0 AND accepted_quantity <> 'NaN'::numeric", name="ck_receipt_items_accepted"),
        sa.CheckConstraint("rejected_quantity >= 0 AND rejected_quantity <> 'NaN'::numeric", name="ck_receipt_items_rejected"),
        sa.CheckConstraint("pending_quantity >= 0 AND pending_quantity <> 'NaN'::numeric", name="ck_receipt_items_pending"),
        sa.CheckConstraint("received_quantity = accepted_quantity + rejected_quantity + pending_quantity", name="ck_receipt_items_balance"),
    )
    for column in ("receipt_id", "product_id", "purchase_order_item_id"):
        op.create_index(f"ix_receipt_items_{column}", "receipt_items", [column])


def downgrade():
    op.drop_table("receipt_items")
    op.drop_table("receipts")
