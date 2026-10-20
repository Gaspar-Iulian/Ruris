"""Add immutable receipt stock movements."""

from alembic import op
import sqlalchemy as sa


revision = "0009_stock_movements"
down_revision = "0008_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("receipt_item_id", sa.BigInteger(), sa.ForeignKey("receipt_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(18, 3), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation_key", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("operation_key", name="uq_stock_movements_operation"),
        sa.CheckConstraint("kind = 'RECEIPT'", name="ck_stock_movements_kind"),
        sa.CheckConstraint("quantity_delta > 0 AND quantity_delta <> 'NaN'::numeric", name="ck_stock_movements_quantity"),
        sa.CheckConstraint("char_length(btrim(reason)) > 0", name="ck_stock_movements_reason"),
    )
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
    op.create_index("ix_stock_movements_receipt_item_id", "stock_movements", ["receipt_item_id"])
    op.execute("""
        CREATE FUNCTION prevent_stock_movement_changes() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Miscarile de stoc nu pot fi modificate sau sterse.';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER stock_movements_append_only
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION prevent_stock_movement_changes()
    """)


def downgrade():
    op.drop_table("stock_movements")
    op.execute("DROP FUNCTION prevent_stock_movement_changes()")
