"""Rename team roles to Romanian."""

from alembic import op
import sqlalchemy as sa


revision = "0004_romanian_roles"
down_revision = "0003_revoked_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.alter_column("users", "role", existing_type=sa.String(10), type_=sa.String(13), existing_nullable=False)
    op.execute("""
        UPDATE users SET role = CASE role
            WHEN 'PURCHASING' THEN 'ACHIZITII'
            WHEN 'WAREHOUSE' THEN 'DEPOZIT'
            WHEN 'ACCOUNTING' THEN 'CONTABILITATE'
            ELSE role END
        WHERE role IN ('PURCHASING', 'WAREHOUSE', 'ACCOUNTING')
    """)
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('ADMIN', 'ACHIZITII', 'DEPOZIT', 'CONTABILITATE')"
    )


def downgrade():
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute("""
        UPDATE users SET role = CASE role
            WHEN 'ACHIZITII' THEN 'PURCHASING'
            WHEN 'DEPOZIT' THEN 'WAREHOUSE'
            WHEN 'CONTABILITATE' THEN 'ACCOUNTING'
            ELSE role END
        WHERE role IN ('ACHIZITII', 'DEPOZIT', 'CONTABILITATE')
    """)
    op.alter_column("users", "role", existing_type=sa.String(13), type_=sa.String(10), existing_nullable=False)
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('ADMIN', 'PURCHASING', 'WAREHOUSE', 'ACCOUNTING')"
    )
