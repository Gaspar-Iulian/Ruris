from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Computed, DateTime, ForeignKey, Identity, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Receipt(db.Model):
    __tablename__ = "receipts"
    __table_args__ = (
        db.UniqueConstraint("number", name="uq_receipts_number"),
        CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')", name="ck_receipts_status"),
        CheckConstraint("version > 0", name="ck_receipts_version"),
        CheckConstraint("char_length(btrim(delivery_reference)) > 0", name="ck_receipts_reference"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[str] = mapped_column(String(40), Computed("'REC-' || id::text", persisted=True))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    delivery_reference: Mapped[str] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="DRAFT", server_default="DRAFT")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    items: Mapped[list["ReceiptItem"]] = relationship(order_by="ReceiptItem.line_number", lazy="selectin")


class ReceiptItem(db.Model):
    __tablename__ = "receipt_items"
    __table_args__ = (
        db.UniqueConstraint("receipt_id", "line_number", name="uq_receipt_items_line"),
        CheckConstraint("line_number > 0", name="ck_receipt_items_line"),
        CheckConstraint("char_length(btrim(description)) > 0", name="ck_receipt_items_description"),
        CheckConstraint("unit IN ('BUC', 'KG', 'L', 'M', 'M2', 'M3')", name="ck_receipt_items_unit"),
        CheckConstraint("received_quantity > 0 AND received_quantity <> 'NaN'::numeric", name="ck_receipt_items_received"),
        CheckConstraint("accepted_quantity >= 0 AND accepted_quantity <> 'NaN'::numeric", name="ck_receipt_items_accepted"),
        CheckConstraint("rejected_quantity >= 0 AND rejected_quantity <> 'NaN'::numeric", name="ck_receipt_items_rejected"),
        CheckConstraint("pending_quantity >= 0 AND pending_quantity <> 'NaN'::numeric", name="ck_receipt_items_pending"),
        CheckConstraint("received_quantity = accepted_quantity + rejected_quantity + pending_quantity", name="ck_receipt_items_balance"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="RESTRICT"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    purchase_order_item_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_items.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(3))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"), server_default=text("0"))
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"), server_default=text("0"))
    pending_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
