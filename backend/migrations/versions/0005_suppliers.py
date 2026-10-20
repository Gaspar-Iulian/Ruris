"""Add suppliers."""

from alembic import op
import sqlalchemy as sa


revision = "0005_suppliers"
down_revision = "0004_romanian_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tax_country", sa.String(2), nullable=False),
        sa.Column("tax_id", sa.String(32), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tax_country", "tax_id", name="uq_suppliers_tax_identity"),
        sa.CheckConstraint("tax_country ~ '^[A-Z]{2}$'", name="ck_suppliers_country"),
        sa.CheckConstraint("tax_id ~ '^[A-Z0-9]{1,32}$' AND left(tax_id, 2) <> tax_country", name="ck_suppliers_tax_id"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_suppliers_name"),
        sa.CheckConstraint("email IS NULL OR email = lower(btrim(email))", name="ck_suppliers_email"),
    )


def downgrade():
    op.drop_table("suppliers")
