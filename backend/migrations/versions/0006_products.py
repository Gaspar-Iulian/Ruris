"""Add products."""

from alembic import op
import sqlalchemy as sa


revision = "0006_products"
down_revision = "0005_suppliers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(3), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
        sa.CheckConstraint("sku ~ '^[A-Z0-9][A-Z0-9._-]{0,63}$'", name="ck_products_sku"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_products_name"),
        sa.CheckConstraint("unit IN ('BUC', 'KG', 'L', 'M', 'M2', 'M3')", name="ck_products_unit"),
    )


def downgrade():
    op.drop_table("products")
