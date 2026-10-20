from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, event, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class AuditEvent(db.Model):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "(actor_user_id IS NOT NULL AND actor_process IS NULL) OR "
            "(actor_user_id IS NULL AND actor_process IS NOT NULL AND btrim(actor_process) <> '')",
            name="ck_audit_events_actor",
        ),
        CheckConstraint("entity_id > 0", name="ck_audit_events_entity_id"),
        CheckConstraint("btrim(action) <> ''", name="ck_audit_events_action"),
        CheckConstraint("btrim(entity_type) <> ''", name="ck_audit_events_entity_type"),
        Index("ix_audit_events_entity", "entity_type", "entity_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_process: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    before_data: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    after_data: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def prevent_audit_changes(mapper, connection, target):
    raise ValueError("Evenimentele de audit nu pot fi modificate sau sterse.")
