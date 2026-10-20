from datetime import datetime
from enum import Enum

import bcrypt
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import Identity, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.extensions import db


class Role(str, Enum):
    ADMIN = "ADMIN"
    PURCHASING = "PURCHASING"
    WAREHOUSE = "WAREHOUSE"
    ACCOUNTING = "ACCOUNTING"


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("email = lower(btrim(email))", name="ck_users_email_normalized"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_users_name_not_empty"),
        CheckConstraint("token_version >= 0", name="ck_users_token_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(60))
    role: Mapped[Role] = mapped_column(
        SQLAlchemyEnum(
            Role,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="ck_users_role",
        )
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @validates("name")
    def validate_name(self, key, value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
            raise ValueError("Numele trebuie sa aiba intre 1 si 120 de caractere.")
        return value.strip()

    @validates("email")
    def validate_email_address(self, key, value):
        if not isinstance(value, str):
            raise ValueError("Adresa de email nu este valida.")
        try:
            email = validate_email(value.strip(), check_deliverability=False).normalized.lower()
        except EmailNotValidError as error:
            raise ValueError("Adresa de email nu este valida.") from error
        if len(email) > 254:
            raise ValueError("Adresa de email este prea lunga.")
        return email

    @validates("role")
    def validate_role(self, key, value):
        try:
            return Role(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Rolul nu este valid.") from error

    def set_password(self, password):
        if not isinstance(password, str) or len(password) < 12:
            raise ValueError("Parola trebuie sa aiba cel putin 12 caractere.")
        encoded = password.encode("utf-8")
        if len(encoded) > 72:
            raise ValueError("Parola poate avea cel mult 72 de octeti UTF-8.")
        self.password_hash = bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("ascii")
        self.token_version = (self.token_version or 0) + 1

    def check_password(self, password):
        if not isinstance(password, str) or not self.password_hash:
            return False
        try:
            encoded = password.encode("utf-8")
            if len(encoded) > 72:
                return False
            return bcrypt.checkpw(encoded, self.password_hash.encode("ascii"))
        except (ValueError, UnicodeError):
            return False
