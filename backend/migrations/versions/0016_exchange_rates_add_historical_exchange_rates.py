"""Add historical exchange rates

Revision ID: 0016_exchange_rates
Revises: 0015_invoice_verification
Create Date: 2026-10-20 20:51:03.003762

"""
from alembic import op
import sqlalchemy as sa


revision = '0016_exchange_rates'
down_revision = '0015_invoice_verification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('exchange_rates',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('rate_date', sa.Date(), nullable=False),
    sa.Column('rate', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('source_url', sa.String(length=200), nullable=False),
    sa.Column('content_sha256', sa.String(length=64), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("rate > 0 AND rate < 'NaN'::numeric", name='ck_exchange_rates_value'),
    sa.CheckConstraint("source = 'BNR' AND currency = 'EUR'", name='ck_exchange_rates_source'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'currency', 'rate_date', name='uq_exchange_rates_source_date')
    )
    op.add_column('invoices', sa.Column('exchange_rate_id', sa.BigInteger(), nullable=True))
    op.add_column('invoices', sa.Column('exchange_rate_value', sa.Numeric(precision=18, scale=6), nullable=True))
    op.add_column('invoices', sa.Column('exchange_rate_date', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('exchange_rate_source', sa.String(length=10), nullable=True))
    op.add_column('invoices', sa.Column('total_ron', sa.Numeric(precision=18, scale=2), nullable=True))
    op.create_foreign_key('fk_invoices_exchange_rate', 'invoices', 'exchange_rates', ['exchange_rate_id'], ['id'], ondelete='RESTRICT')

    op.create_check_constraint("ck_invoices_conversion", "invoices", "(exchange_rate_value IS NULL AND exchange_rate_date IS NULL AND exchange_rate_id IS NULL AND exchange_rate_source IS NULL AND total_ron IS NULL) OR (exchange_rate_value IS NOT NULL AND exchange_rate_date IS NOT NULL AND exchange_rate_source IS NOT NULL AND total_ron IS NOT NULL AND exchange_rate_value > 0 AND exchange_rate_value < 'NaN'::numeric AND total_ron >= 0 AND total_ron < 'NaN'::numeric AND exchange_rate_date = invoice_date AND ((currency = 'RON' AND exchange_rate_value = 1 AND exchange_rate_source = 'IDENTITY' AND exchange_rate_id IS NULL) OR (currency = 'EUR' AND exchange_rate_source = 'BNR' AND exchange_rate_id IS NOT NULL)))")
    op.execute("""CREATE FUNCTION prevent_exchange_rate_changes() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Cursurile istorice nu pot fi modificate sau sterse.'; END; $$""")
    op.execute("CREATE TRIGGER exchange_rates_append_only BEFORE UPDATE OR DELETE ON exchange_rates FOR EACH ROW EXECUTE FUNCTION prevent_exchange_rate_changes()")


def downgrade():
    op.drop_constraint("ck_invoices_conversion", "invoices", type_="check")
    op.drop_constraint('fk_invoices_exchange_rate', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'total_ron')
    op.drop_column('invoices', 'exchange_rate_source')
    op.drop_column('invoices', 'exchange_rate_date')
    op.drop_column('invoices', 'exchange_rate_value')
    op.drop_column('invoices', 'exchange_rate_id')
    op.drop_table('exchange_rates')
    op.execute('DROP FUNCTION prevent_exchange_rate_changes()')
