"""Add users."""

from alembic import op
import sqlalchemy as sa


revision = "0001_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(60), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "ADMIN", "PURCHASING", "WAREHOUSE", "ACCOUNTING",
                name="ck_users_role", native_enum=False, create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("email = lower(btrim(email))", name="ck_users_email_normalized"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_users_name_not_empty"),
        sa.CheckConstraint("token_version >= 0", name="ck_users_token_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )


def downgrade():
    op.drop_table("users")
