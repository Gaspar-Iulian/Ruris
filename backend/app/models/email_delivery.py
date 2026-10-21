from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class EmailOutbox(db.Model):
    __tablename__ = "email_outbox"
    __table_args__ = (
        db.UniqueConstraint("kind", "transport", "as_of", "recipient_user_id", name="uq_email_outbox_daily"),
        CheckConstraint("kind IN ('OVERDUE', 'BLOCKED_INVOICES')", name="ck_email_outbox_kind"),
        CheckConstraint("transport = 'LOCAL_MAILPIT'", name="ck_email_outbox_transport"),
        CheckConstraint("status IN ('PENDING', 'SENDING', 'SENT', 'FAILED', 'UNKNOWN', 'SKIPPED')", name="ck_email_outbox_status"),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= 3", name="ck_email_outbox_attempts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    transport: Mapped[str] = mapped_column(String(20))
    as_of: Mapped[date] = mapped_column(Date)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    recipient_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="PENDING", server_default="PENDING", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(String(80))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmailAttempt(db.Model):
    __tablename__ = "email_attempts"
    __table_args__ = (
        db.UniqueConstraint("outbox_id", "attempt_number", name="uq_email_attempts_number"),
        CheckConstraint("attempt_number BETWEEN 1 AND 3", name="ck_email_attempts_number"),
        CheckConstraint("status IN ('SENDING', 'SENT', 'FAILED', 'UNKNOWN')", name="ck_email_attempts_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    outbox_id: Mapped[int] = mapped_column(ForeignKey("email_outbox.id", ondelete="RESTRICT"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12))
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
