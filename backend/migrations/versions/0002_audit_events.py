"""Adauga jurnalul de audit."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_audit_events"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_process", sa.String(80), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("before_data", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("after_data", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(actor_user_id IS NOT NULL AND actor_process IS NULL) OR "
            "(actor_user_id IS NULL AND actor_process IS NOT NULL AND btrim(actor_process) <> '')",
            name="ck_audit_events_actor",
        ),
        sa.CheckConstraint("entity_id > 0", name="ck_audit_events_entity_id"),
        sa.CheckConstraint("btrim(action) <> ''", name="ck_audit_events_action"),
        sa.CheckConstraint("btrim(entity_type) <> ''", name="ck_audit_events_entity_type"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id", "created_at"])
    op.execute("""
        CREATE FUNCTION prevent_audit_event_changes() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Evenimentele de audit nu pot fi modificate sau sterse.';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_changes()
    """)


def downgrade():
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION prevent_audit_event_changes()")
