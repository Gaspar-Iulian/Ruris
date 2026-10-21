"""Add invoice payment recording

Revision ID: 0018_invoice_payment
Revises: 0017_invoice_approval
Create Date: 2026-10-20 21:05:52.079921

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0018_invoice_payment'
down_revision = '0017_invoice_approval'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('paid_by_id', sa.BigInteger(), nullable=True))
    op.add_column('invoices', sa.Column('payment_reference', sa.String(length=120), nullable=True))
    op.create_foreign_key('fk_invoices_paid_by', 'invoices', 'users', ['paid_by_id'], ['id'], ondelete='RESTRICT')

    op.drop_constraint('ck_invoices_approval', "invoices", type_="check")
    op.create_check_constraint('ck_invoices_approval', "invoices", "(status IN ('APPROVED', 'PAID') AND approved_by_id IS NOT NULL AND approved_at IS NOT NULL AND total_ron IS NOT NULL) OR (status NOT IN ('APPROVED', 'PAID') AND approved_by_id IS NULL AND approved_at IS NULL)")
    op.create_check_constraint('ck_invoices_payment', "invoices", "(status = 'PAID' AND paid_at IS NOT NULL AND paid_by_id IS NOT NULL AND payment_reference IS NOT NULL AND length(btrim(payment_reference)) BETWEEN 1 AND 120 AND paid_at >= approved_at) OR (status <> 'PAID' AND paid_at IS NULL AND paid_by_id IS NULL AND payment_reference IS NULL)")
    op.drop_constraint('ck_invoices_status', "invoices", type_="check")
    op.create_check_constraint('ck_invoices_status', "invoices", "status IN ('DRAFT', 'BLOCKED', 'VERIFIED', 'APPROVED', 'PAID')")


def downgrade():
    op.drop_constraint("ck_invoices_payment", "invoices", type_="check")
    op.drop_constraint('ck_invoices_status', "invoices", type_="check")
    op.create_check_constraint('ck_invoices_status', "invoices", "status IN ('DRAFT', 'BLOCKED', 'VERIFIED', 'APPROVED')")
    op.drop_constraint('ck_invoices_approval', "invoices", type_="check")
    op.create_check_constraint('ck_invoices_approval', "invoices", "(status IN ('APPROVED') AND approved_by_id IS NOT NULL AND approved_at IS NOT NULL AND total_ron IS NOT NULL) OR (status NOT IN ('APPROVED') AND approved_by_id IS NULL AND approved_at IS NULL)")

    op.drop_constraint('fk_invoices_paid_by', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'payment_reference')
    op.drop_column('invoices', 'paid_by_id')
    op.drop_column('invoices', 'paid_at')
