from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest

from app.extensions import db
from app.models import EmailAttempt, EmailOutbox, Role
from app.permissions import roles_required
from app.routes.pagination import pagination_args
from app.services.notification_kinds import RECIPIENT_ROLES


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("")
@roles_required(Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE)
def index():
    try:
        pagination = pagination_args(request.args)
    except BadRequest as error:
        return jsonify(message=error.description), 400
    try:
        kinds = [kind for kind, role in RECIPIENT_ROLES.items() if role == current_user.role]
        condition = (EmailOutbox.recipient_user_id == current_user.id, EmailOutbox.kind.in_(kinds))
        rows = db.session.scalars(select(EmailOutbox).where(*condition).order_by(EmailOutbox.id.desc())
            .offset((pagination["page"] - 1) * pagination["per_page"]).limit(pagination["per_page"])).all()
        attempts = db.session.scalars(select(EmailAttempt).where(EmailAttempt.outbox_id.in_([row.id for row in rows]))
            .order_by(EmailAttempt.outbox_id, EmailAttempt.attempt_number)).all()
        grouped = {}
        for attempt in attempts:
            grouped.setdefault(attempt.outbox_id, []).append({"number": attempt.attempt_number, "status": attempt.status,
                "error_code": attempt.error_code, "started_at": attempt.started_at.isoformat(),
                "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None})
        notifications = [{"id": row.id, "kind": row.kind, "subject": row.subject, "body": row.body,
            "as_of": row.as_of.isoformat(), "transport": row.transport, "status": row.status, "attempt_count": row.attempt_count,
            "last_error": row.last_error, "created_at": row.created_at.isoformat(),
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
            "attempts": grouped.get(row.id, [])} for row in rows]
        return jsonify(notifications=notifications, total=db.session.scalar(select(func.count()).select_from(EmailOutbox).where(*condition)), **pagination)
    except SQLAlchemyError:
        return jsonify(message="Notificarile nu sunt disponibile momentan."), 503


@notifications_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
