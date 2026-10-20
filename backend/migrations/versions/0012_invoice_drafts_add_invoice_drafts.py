"""Add invoice drafts

Revision ID: 0012_invoice_drafts
Revises: 0011_email_retry_schedule
Create Date: 2026-10-20 20:09:40.927029

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0012_invoice_drafts'
down_revision = '0011_email_retry_schedule'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('invoices',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('supplier_id', sa.BigInteger(), nullable=False),
    sa.Column('series', sa.String(length=40), nullable=False),
    sa.Column('number', sa.String(length=80), nullable=False),
    sa.Column('invoice_date', sa.Date(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('net_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('vat_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='DRAFT', nullable=False),
    sa.Column('created_by_id', sa.BigInteger(), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency IN ('RON', 'EUR')", name='ck_invoices_currency'),
    sa.CheckConstraint("net_amount >= 0 AND vat_amount >= 0 AND total_amount = net_amount + vat_amount AND total_amount < 'NaN'::numeric", name='ck_invoices_amounts'),
    sa.CheckConstraint("status = 'DRAFT'", name='ck_invoices_status'),
    sa.CheckConstraint('due_date >= invoice_date', name='ck_invoices_dates'),
    sa.CheckConstraint('length(number) BETWEEN 1 AND 80', name='ck_invoices_number'),
    sa.CheckConstraint('version > 0', name='ck_invoices_version'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('supplier_id', 'series', 'number', name='uq_invoices_supplier_reference')
    )
    op.create_index(op.f('ix_invoices_supplier_id'), 'invoices', ['supplier_id'], unique=False)
    op.create_table('invoice_items',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('invoice_id', sa.BigInteger(), nullable=False),
    sa.Column('line_number', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('unit', sa.String(length=10), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('vat_rate', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('net_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('vat_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.CheckConstraint("net_amount >= 0 AND vat_amount >= 0 AND total_amount = net_amount + vat_amount AND total_amount < 'NaN'::numeric", name='ck_invoice_items_amounts'),
    sa.CheckConstraint("quantity > 0 AND quantity < 'NaN'::numeric AND unit_price >= 0 AND unit_price < 'NaN'::numeric AND vat_rate BETWEEN 0 AND 100", name='ck_invoice_items_values'),
    sa.CheckConstraint('line_number BETWEEN 1 AND 100', name='ck_invoice_items_line'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('invoice_id', 'line_number', name='uq_invoice_items_line')
    )
    op.create_index(op.f('ix_invoice_items_invoice_id'), 'invoice_items', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_items_product_id'), 'invoice_items', ['product_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_invoice_items_product_id'), table_name='invoice_items')
    op.drop_index(op.f('ix_invoice_items_invoice_id'), table_name='invoice_items')
    op.drop_table('invoice_items')
    op.drop_index(op.f('ix_invoices_supplier_id'), table_name='invoices')
    op.drop_table('invoices')

