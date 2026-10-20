import re
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.extensions import db


PRODUCT_UNITS = ("BUC", "KG", "L", "M", "M2", "M3")


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (
        db.UniqueConstraint("sku", name="uq_products_sku"),
        CheckConstraint("sku ~ '^[A-Z0-9][A-Z0-9._-]{0,63}$'", name="ck_products_sku"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_products_name"),
        CheckConstraint("unit IN ('BUC', 'KG', 'L', 'M', 'M2', 'M3')", name="ck_products_unit"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @validates("sku")
    def validate_sku(self, key, value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,63}", value.strip().upper()):
            raise ValueError("Codul trebuie sa aiba 1-64 de caractere: litere, cifre, punct, cratima sau underscore; primul caracter trebuie sa fie litera sau cifra.")
        return value.strip().upper()

    @validates("name")
    def validate_name(self, key, value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
            raise ValueError("Numele trebuie sa aiba intre 1 si 200 de caractere.")
        return value.strip()

    @validates("unit")
    def validate_unit(self, key, value):
        if not isinstance(value, str) or value.strip().upper() not in PRODUCT_UNITS:
            raise ValueError("Unitatea trebuie sa fie BUC, KG, L, M, M2 sau M3.")
        return value.strip().upper()
