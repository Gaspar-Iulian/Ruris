"""Add invoice allocations

Revision ID: 0014_invoice_allocations
Revises: 0013_invoice_line_order
Create Date: 2026-10-20 20:22:49.703526

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0014_invoice_allocations'
down_revision = '0013_invoice_line_order'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('invoice_allocations',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('invoice_item_id', sa.BigInteger(), nullable=False),
    sa.Column('receipt_item_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('status', sa.String(length=8), server_default='ACTIVE', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(status = 'ACTIVE' AND released_at IS NULL) OR (status = 'RELEASED' AND released_at IS NOT NULL)", name='ck_invoice_allocations_release'),
    sa.CheckConstraint("quantity > 0 AND quantity < 'NaN'::numeric", name='ck_invoice_allocations_quantity'),
    sa.CheckConstraint("status IN ('ACTIVE', 'RELEASED')", name='ck_invoice_allocations_status'),
    sa.ForeignKeyConstraint(['invoice_item_id'], ['invoice_items.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['receipt_item_id'], ['receipt_items.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoice_allocations_invoice_item_id'), 'invoice_allocations', ['invoice_item_id'], unique=False)
    op.create_index(op.f('ix_invoice_allocations_receipt_item_id'), 'invoice_allocations', ['receipt_item_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_invoice_allocations_receipt_item_id'), table_name='invoice_allocations')
    op.drop_index(op.f('ix_invoice_allocations_invoice_item_id'), table_name='invoice_allocations')
    op.drop_table('invoice_allocations')
