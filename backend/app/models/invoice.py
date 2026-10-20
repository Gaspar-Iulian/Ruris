from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Invoice(db.Model):
    __tablename__ = "invoices"
    __table_args__ = (
        db.UniqueConstraint("supplier_id", "series", "number", name="uq_invoices_supplier_reference"),
        CheckConstraint("currency IN ('RON', 'EUR')", name="ck_invoices_currency"),
        CheckConstraint("status = 'DRAFT'", name="ck_invoices_status"),
        CheckConstraint("due_date >= invoice_date", name="ck_invoices_dates"),
        CheckConstraint("version > 0", name="ck_invoices_version"),
        CheckConstraint("length(number) BETWEEN 1 AND 80", name="ck_invoices_number"),
        CheckConstraint("net_amount >= 0 AND vat_amount >= 0 AND total_amount = net_amount + vat_amount AND total_amount < 'NaN'::numeric", name="ck_invoices_amounts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    series: Mapped[str] = mapped_column(String(40))
    number: Mapped[str] = mapped_column(String(80))
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT", server_default="DRAFT")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    items: Mapped[list["InvoiceItem"]] = relationship(order_by="InvoiceItem.line_number", lazy="selectin")


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    __table_args__ = (
        db.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_items_line"),
        CheckConstraint("line_number > 0", name="ck_invoice_items_line"),
        CheckConstraint("quantity > 0 AND quantity < 'NaN'::numeric AND unit_price >= 0 AND unit_price < 'NaN'::numeric AND vat_rate BETWEEN 0 AND 100", name="ck_invoice_items_values"),
        CheckConstraint("net_amount >= 0 AND vat_amount >= 0 AND total_amount = net_amount + vat_amount AND total_amount < 'NaN'::numeric", name="ck_invoice_items_amounts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
