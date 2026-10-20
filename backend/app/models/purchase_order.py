from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Computed, Date, DateTime, ForeignKey, Identity, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        db.UniqueConstraint("number", name="uq_purchase_orders_number"),
        CheckConstraint("currency IN ('RON', 'EUR')", name="ck_purchase_orders_currency"),
        CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CLOSED', 'CANCELLED')", name="ck_purchase_orders_status"),
        CheckConstraint("version > 0", name="ck_purchase_orders_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[str] = mapped_column(String(40), Computed("'CA-' || id::text", persisted=True))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(10), default="DRAFT", server_default="DRAFT")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    items: Mapped[list["PurchaseOrderItem"]] = relationship(order_by="PurchaseOrderItem.line_number", lazy="selectin")


class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        db.UniqueConstraint("purchase_order_id", "line_number", name="uq_purchase_order_items_line"),
        CheckConstraint("line_number > 0", name="ck_purchase_order_items_line"),
        CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="ck_purchase_order_items_quantity"),
        CheckConstraint("unit_price >= 0 AND unit_price <> 'NaN'::numeric", name="ck_purchase_order_items_price"),
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100 AND vat_rate <> 'NaN'::numeric", name="ck_purchase_order_items_vat"),
        CheckConstraint("char_length(btrim(description)) > 0", name="ck_purchase_order_items_description"),
        CheckConstraint("unit IN ('BUC', 'KG', 'L', 'M', 'M2', 'M3')", name="ck_purchase_order_items_unit"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(3))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    expected_date: Mapped[date] = mapped_column(Date)
