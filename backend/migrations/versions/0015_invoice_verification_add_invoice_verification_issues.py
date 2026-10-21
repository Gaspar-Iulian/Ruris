"""Add invoice verification issues

Revision ID: 0015_invoice_verification
Revises: 0014_invoice_allocations
Create Date: 2026-10-20 20:36:47.408542

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0015_invoice_verification'
down_revision = '0014_invoice_allocations'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_invoices_status', 'invoices', type_='check')
    op.create_check_constraint('ck_invoices_status', 'invoices', "status IN ('DRAFT', 'BLOCKED', 'VERIFIED')")
    op.create_table('invoice_issues',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('invoice_id', sa.BigInteger(), nullable=False),
    sa.Column('invoice_item_id', sa.BigInteger(), nullable=True),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('details', sa.String(length=1000), nullable=False),
    sa.Column('responsible_role', sa.String(length=20), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolution', sa.String(length=12), nullable=True),
    sa.CheckConstraint("(resolved_at IS NULL AND resolution IS NULL) OR (resolved_at IS NOT NULL AND resolution IS NOT NULL AND resolution IN ('RESOLVED', 'SUPERSEDED'))", name='ck_invoice_issues_resolution'),
    sa.CheckConstraint("responsible_role IN ('CONTABILITATE', 'ACHIZITII', 'DEPOZIT')", name='ck_invoice_issues_role'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['invoice_item_id'], ['invoice_items.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoice_issues_invoice_id'), 'invoice_issues', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_issues_invoice_item_id'), 'invoice_issues', ['invoice_item_id'], unique=False)


def downgrade():
    op.drop_constraint('ck_invoices_status', 'invoices', type_='check')
    op.create_check_constraint('ck_invoices_status', 'invoices', "status = 'DRAFT'")
    op.drop_index(op.f('ix_invoice_issues_invoice_item_id'), table_name='invoice_issues')
    op.drop_index(op.f('ix_invoice_issues_invoice_id'), table_name='invoice_issues')
    op.drop_table('invoice_issues')
