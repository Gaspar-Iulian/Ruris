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
        CheckConstraint("status IN ('DRAFT', 'BLOCKED', 'VERIFIED', 'APPROVED', 'PAID', 'CANCELLED')", name="ck_invoices_status"),
        CheckConstraint("(status = 'CANCELLED' AND cancelled_by_id IS NOT NULL AND cancelled_at IS NOT NULL "
                        "AND cancellation_reason IS NOT NULL AND length(btrim(cancellation_reason)) BETWEEN 1 AND 1000) OR "
                        "(status <> 'CANCELLED' AND cancelled_by_id IS NULL AND cancelled_at IS NULL AND cancellation_reason IS NULL)", name="ck_invoices_cancellation"),
        CheckConstraint("(status IN ('APPROVED', 'PAID') AND approved_by_id IS NOT NULL AND approved_at IS NOT NULL AND total_ron IS NOT NULL) OR (status NOT IN ('APPROVED', 'PAID') AND approved_by_id IS NULL AND approved_at IS NULL)", name="ck_invoices_approval"),
        CheckConstraint("(status = 'PAID' AND paid_at IS NOT NULL AND paid_by_id IS NOT NULL AND payment_reference IS NOT NULL AND length(btrim(payment_reference)) BETWEEN 1 AND 120 AND paid_at >= approved_at) OR (status <> 'PAID' AND paid_at IS NULL AND paid_by_id IS NULL AND payment_reference IS NULL)", name="ck_invoices_payment"),
        CheckConstraint("due_date >= invoice_date", name="ck_invoices_dates"),
        CheckConstraint("version > 0", name="ck_invoices_version"),
        CheckConstraint("length(number) BETWEEN 1 AND 80", name="ck_invoices_number"),
        CheckConstraint("net_amount >= 0 AND vat_amount >= 0 AND total_amount = net_amount + vat_amount AND total_amount < 'NaN'::numeric", name="ck_invoices_amounts"),
        CheckConstraint("(declared_net_amount IS NULL AND declared_vat_amount IS NULL AND declared_total_amount IS NULL) OR (declared_net_amount IS NOT NULL AND declared_vat_amount IS NOT NULL AND declared_total_amount IS NOT NULL AND declared_net_amount >= 0 AND declared_net_amount < 'NaN'::numeric AND declared_vat_amount >= 0 AND declared_vat_amount < 'NaN'::numeric AND declared_total_amount >= 0 AND declared_total_amount < 'NaN'::numeric)", name="ck_invoices_declared_amounts"),
        CheckConstraint("(exchange_rate_value IS NULL AND exchange_rate_date IS NULL AND exchange_rate_id IS NULL AND exchange_rate_source IS NULL AND total_ron IS NULL) OR (exchange_rate_value IS NOT NULL AND exchange_rate_date IS NOT NULL AND exchange_rate_source IS NOT NULL AND total_ron IS NOT NULL AND exchange_rate_value > 0 AND exchange_rate_value < 'NaN'::numeric AND total_ron >= 0 AND total_ron < 'NaN'::numeric AND exchange_rate_date = invoice_date AND ((currency = 'RON' AND exchange_rate_value = 1 AND exchange_rate_source = 'IDENTITY' AND exchange_rate_id IS NULL) OR (currency = 'EUR' AND exchange_rate_source = 'BNR' AND exchange_rate_id IS NOT NULL)))", name="ck_invoices_conversion"),
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
    declared_net_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    declared_vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    declared_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    exchange_rate_id: Mapped[int | None] = mapped_column(ForeignKey("exchange_rates.id", ondelete="RESTRICT"))
    exchange_rate_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    exchange_rate_date: Mapped[date | None] = mapped_column(Date)
    exchange_rate_source: Mapped[str | None] = mapped_column(String(10))
    total_ron: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT", server_default="DRAFT")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT", name="fk_invoices_approved_by"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT", name="fk_invoices_paid_by"))
    payment_reference: Mapped[str | None] = mapped_column(String(120))
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT", name="fk_invoices_cancelled_by"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(1000))
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
    purchase_order_item_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_items.id", ondelete="RESTRICT", name="fk_invoice_items_order_item"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
