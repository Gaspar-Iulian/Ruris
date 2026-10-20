from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class RevokedToken(db.Model):
    __tablename__ = "revoked_tokens"
    __table_args__ = (
        UniqueConstraint("token_jti", name="uq_revoked_tokens_jti"),
        Index("ix_revoked_tokens_expires_at", "expires_at"),
        Index("ix_revoked_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    token_jti: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
