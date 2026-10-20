from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Numeric, String, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    __table_args__ = (
        db.UniqueConstraint("operation_key", name="uq_stock_movements_operation"),
        CheckConstraint("kind = 'RECEIPT'", name="ck_stock_movements_kind"),
        CheckConstraint("quantity_delta > 0 AND quantity_delta <> 'NaN'::numeric", name="ck_stock_movements_quantity"),
        CheckConstraint("char_length(btrim(reason)) > 0", name="ck_stock_movements_reason"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    receipt_item_id: Mapped[int] = mapped_column(ForeignKey("receipt_items.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reason: Mapped[str] = mapped_column(String(1000))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    operation_key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@event.listens_for(StockMovement, "before_update")
@event.listens_for(StockMovement, "before_delete")
def prevent_stock_changes(mapper, connection, target):
    raise ValueError("Miscarile de stoc nu pot fi modificate sau sterse.")
