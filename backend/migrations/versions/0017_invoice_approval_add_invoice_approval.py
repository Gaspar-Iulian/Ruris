"""Add invoice approval

Revision ID: 0017_invoice_approval
Revises: 0016_exchange_rates
Create Date: 2026-10-20 21:00:44.531437

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0017_invoice_approval'
down_revision = '0016_exchange_rates'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('approved_by_id', sa.BigInteger(), nullable=True))
    op.add_column('invoices', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('fk_invoices_approved_by', 'invoices', 'users', ['approved_by_id'], ['id'], ondelete='RESTRICT')

    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.create_check_constraint("ck_invoices_status", "invoices", "status IN ('DRAFT', 'BLOCKED', 'VERIFIED', 'APPROVED')")
    op.create_check_constraint("ck_invoices_approval", "invoices", "(status = 'APPROVED' AND approved_by_id IS NOT NULL AND approved_at IS NOT NULL AND total_ron IS NOT NULL) OR (status <> 'APPROVED' AND approved_by_id IS NULL AND approved_at IS NULL)")


def downgrade():
    op.drop_constraint("ck_invoices_approval", "invoices", type_="check")
    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.create_check_constraint("ck_invoices_status", "invoices", "status IN ('DRAFT', 'BLOCKED', 'VERIFIED')")
    op.drop_constraint('fk_invoices_approved_by', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'approved_at')
    op.drop_column('invoices', 'approved_by_id')
