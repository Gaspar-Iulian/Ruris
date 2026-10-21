from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class InvoiceIssue(db.Model):
    __tablename__ = "invoice_issues"
    __table_args__ = (
        CheckConstraint("responsible_role IN ('CONTABILITATE', 'ACHIZITII', 'DEPOZIT')", name="ck_invoice_issues_role"),
        CheckConstraint("(resolved_at IS NULL AND resolution IS NULL) OR (resolved_at IS NOT NULL AND resolution IS NOT NULL AND resolution IN ('RESOLVED', 'SUPERSEDED'))", name="ck_invoice_issues_resolution"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    invoice_item_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_items.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    details: Mapped[str] = mapped_column(String(1000))
    responsible_role: Mapped[str] = mapped_column(String(20))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(12))
