"""Add retained document attachments."""

from alembic import op
import sqlalchemy as sa

revision = "0024_document_attachments"
down_revision = "0023_invoice_declared_totals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("attachments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("purchase_order_id", sa.BigInteger(), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT")),
        sa.Column("receipt_id", sa.BigInteger(), sa.ForeignKey("receipts.id", ondelete="RESTRICT")),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id", ondelete="RESTRICT")),
        sa.Column("storage_key", sa.String(64), nullable=False),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("upload_key", sa.String(36), nullable=False),
        sa.Column("upload_reason", sa.Text(), nullable=False),
        sa.Column("uploaded_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column("status", sa.String(12), server_default="ACTIVE", nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_by_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("withdrawal_reason", sa.Text()),
        sa.CheckConstraint("num_nonnulls(purchase_order_id, receipt_id, invoice_id) = 1", name="ck_attachments_parent"),
        sa.CheckConstraint("storage_key ~ '^[a-f0-9]{64}$'", name="ck_attachments_storage_key"),
        sa.CheckConstraint("content_sha256 ~ '^[a-f0-9]{64}$'", name="ck_attachments_hash"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 10485760", name="ck_attachments_size"),
        sa.CheckConstraint("media_type IN ('application/pdf', 'image/png', 'image/jpeg')", name="ck_attachments_media_type"),
        sa.CheckConstraint("length(btrim(original_name)) BETWEEN 1 AND 200", name="ck_attachments_name"),
        sa.CheckConstraint("length(btrim(upload_reason)) BETWEEN 1 AND 1000", name="ck_attachments_reason"),
        sa.CheckConstraint("upload_key ~ '^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$'", name="ck_attachments_upload_key"),
        sa.CheckConstraint("(status = 'ACTIVE' AND withdrawn_at IS NULL AND withdrawn_by_id IS NULL AND withdrawal_reason IS NULL) OR (status = 'WITHDRAWN' AND withdrawn_at IS NOT NULL AND withdrawn_at >= created_at AND withdrawn_by_id IS NOT NULL AND withdrawal_reason IS NOT NULL AND length(btrim(withdrawal_reason)) BETWEEN 1 AND 1000)", name="ck_attachments_withdrawal"),
        sa.UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
        sa.UniqueConstraint("uploaded_by_id", "upload_key", name="uq_attachments_upload_key"))
    for column in ("purchase_order_id", "receipt_id", "invoice_id"):
        op.create_index(f"ix_attachments_{column}", "attachments", [column])
    op.execute("""
        CREATE FUNCTION protect_attachment_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Attachment history cannot be deleted.';
            END IF;
            IF OLD.status <> 'ACTIVE' OR NEW.status <> 'WITHDRAWN' OR
               (to_jsonb(NEW) - ARRAY['status', 'withdrawn_at', 'withdrawn_by_id', 'withdrawal_reason'])
               IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['status', 'withdrawn_at', 'withdrawn_by_id', 'withdrawal_reason']) THEN
                RAISE EXCEPTION 'Only attachment withdrawal is allowed.';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER attachments_retained BEFORE UPDATE OR DELETE ON attachments FOR EACH ROW EXECUTE FUNCTION protect_attachment_history()")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM attachments)")):
        raise RuntimeError("Attachment history must be retained before downgrade.")
    op.drop_table("attachments")
    op.execute("DROP FUNCTION protect_attachment_history()")
