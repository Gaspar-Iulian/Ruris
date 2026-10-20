"""Add purchase order drafts."""

from alembic import op
import sqlalchemy as sa


revision = "0007_purchase_orders"
down_revision = "0006_products"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("number", sa.String(40), sa.Computed("'CA-' || id::text", persisted=True), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(10), server_default="DRAFT", nullable=False),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("number", name="uq_purchase_orders_number"),
        sa.CheckConstraint("currency IN ('RON', 'EUR')", name="ck_purchase_orders_currency"),
        sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CLOSED', 'CANCELLED')", name="ck_purchase_orders_status"),
        sa.CheckConstraint("version > 0", name="ck_purchase_orders_version"),
    )
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("purchase_order_id", sa.BigInteger(), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(3), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("purchase_order_id", "line_number", name="uq_purchase_order_items_line"),
        sa.CheckConstraint("line_number > 0", name="ck_purchase_order_items_line"),
        sa.CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="ck_purchase_order_items_quantity"),
        sa.CheckConstraint("unit_price >= 0 AND unit_price <> 'NaN'::numeric", name="ck_purchase_order_items_price"),
        sa.CheckConstraint("vat_rate >= 0 AND vat_rate <= 100 AND vat_rate <> 'NaN'::numeric", name="ck_purchase_order_items_vat"),
        sa.CheckConstraint("char_length(btrim(description)) > 0", name="ck_purchase_order_items_description"),
        sa.CheckConstraint("unit IN ('BUC', 'KG', 'L', 'M', 'M2', 'M3')", name="ck_purchase_order_items_unit"),
    )
    op.create_index("ix_purchase_order_items_purchase_order_id", "purchase_order_items", ["purchase_order_id"])
    op.create_index("ix_purchase_order_items_product_id", "purchase_order_items", ["product_id"])


def downgrade():
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
