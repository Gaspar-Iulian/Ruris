from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Attachment(db.Model):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("num_nonnulls(purchase_order_id, receipt_id, invoice_id) = 1", name="ck_attachments_parent"),
        CheckConstraint("storage_key ~ '^[a-f0-9]{64}$'", name="ck_attachments_storage_key"),
        CheckConstraint("content_sha256 ~ '^[a-f0-9]{64}$'", name="ck_attachments_hash"),
        CheckConstraint("size_bytes BETWEEN 1 AND 10485760", name="ck_attachments_size"),
        CheckConstraint("media_type IN ('application/pdf', 'image/png', 'image/jpeg')", name="ck_attachments_media_type"),
        CheckConstraint("length(btrim(original_name)) BETWEEN 1 AND 200", name="ck_attachments_name"),
        CheckConstraint("length(btrim(upload_reason)) BETWEEN 1 AND 1000", name="ck_attachments_reason"),
        CheckConstraint("upload_key ~ '^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$'", name="ck_attachments_upload_key"),
        CheckConstraint("(status = 'ACTIVE' AND withdrawn_at IS NULL AND withdrawn_by_id IS NULL AND withdrawal_reason IS NULL) OR (status = 'WITHDRAWN' AND withdrawn_at IS NOT NULL AND withdrawn_at >= created_at AND withdrawn_by_id IS NOT NULL AND withdrawal_reason IS NOT NULL AND length(btrim(withdrawal_reason)) BETWEEN 1 AND 1000)", name="ck_attachments_withdrawal"),
        UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
        UniqueConstraint("uploaded_by_id", "upload_key", name="uq_attachments_upload_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True)
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id", ondelete="RESTRICT"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    storage_key: Mapped[str] = mapped_column(String(64))
    original_name: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(30))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    upload_key: Mapped[str] = mapped_column(String(36))
    upload_reason: Mapped[str] = mapped_column(Text)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", server_default="ACTIVE")
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    withdrawal_reason: Mapped[str | None] = mapped_column(Text)
