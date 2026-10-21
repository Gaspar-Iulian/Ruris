from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Identity, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ExchangeRate(db.Model):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        db.UniqueConstraint("source", "currency", "rate_date", name="uq_exchange_rates_source_date"),
        CheckConstraint("source = 'BNR' AND currency = 'EUR'", name="ck_exchange_rates_source"),
        CheckConstraint("rate > 0 AND rate < 'NaN'::numeric", name="ck_exchange_rates_value"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    source: Mapped[str] = mapped_column(String(10))
    source_url: Mapped[str] = mapped_column(String(200))
    content_sha256: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
