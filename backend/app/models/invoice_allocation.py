from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class InvoiceAllocation(db.Model):
    __tablename__ = "invoice_allocations"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity < 'NaN'::numeric", name="ck_invoice_allocations_quantity"),
        CheckConstraint("status IN ('ACTIVE', 'RELEASED')", name="ck_invoice_allocations_status"),
        CheckConstraint("(status = 'ACTIVE' AND released_at IS NULL) OR (status = 'RELEASED' AND released_at IS NOT NULL)", name="ck_invoice_allocations_release"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    invoice_item_id: Mapped[int] = mapped_column(ForeignKey("invoice_items.id", ondelete="RESTRICT"), index=True)
    receipt_item_id: Mapped[int] = mapped_column(ForeignKey("receipt_items.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
