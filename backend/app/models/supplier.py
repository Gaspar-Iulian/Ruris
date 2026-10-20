import re
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.extensions import db
from app.models.user import normalize_email


def normalize_tax_identity(country, tax_id):
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country.strip().upper()):
        raise ValueError("Tara trebuie sa contina doua litere, de exemplu RO.")
    country = country.strip().upper()
    if not isinstance(tax_id, str):
        raise ValueError("Codul fiscal trebuie sa fie text.")
    tax_id = re.sub(r"\s+", "", tax_id).upper()
    if tax_id.startswith(country):
        tax_id = tax_id[2:]
    if not re.fullmatch(r"[A-Z0-9]{1,32}", tax_id) or tax_id.startswith(country):
        raise ValueError("Codul fiscal trebuie sa contina intre 1 si 32 de litere sau cifre, fara prefix repetat.")
    return country, tax_id


class Supplier(db.Model):
    __tablename__ = "suppliers"
    __table_args__ = (
        db.UniqueConstraint("tax_country", "tax_id", name="uq_suppliers_tax_identity"),
        CheckConstraint("tax_country ~ '^[A-Z]{2}$'", name="ck_suppliers_country"),
        CheckConstraint("tax_id ~ '^[A-Z0-9]{1,32}$' AND left(tax_id, 2) <> tax_country", name="ck_suppliers_tax_id"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_suppliers_name"),
        CheckConstraint("email IS NULL OR email = lower(btrim(email))", name="ck_suppliers_email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_country: Mapped[str] = mapped_column(String(2))
    tax_id: Mapped[str] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @validates("name")
    def validate_name(self, key, value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
            raise ValueError("Numele trebuie sa aiba intre 1 si 200 de caractere.")
        return value.strip()

    @validates("email")
    def validate_email(self, key, value):
        if value is None or isinstance(value, str) and not value.strip():
            return None
        return normalize_email(value)
