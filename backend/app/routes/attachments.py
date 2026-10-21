from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import current_user
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.extensions import db
from app.models import Role
from app.permissions import roles_required
from app.routes.pagination import pagination_args
from app.services.attachments import AttachmentConflict, AttachmentForbidden, AttachmentNotFound
from app.services.attachments import check_role, download_attachment, list_attachments, upload_attachment, withdraw_attachment
from app.services.attachment_storage import AttachmentStorageError, AttachmentTooLarge, MAX_FILE_BYTES


attachments_bp = Blueprint("attachments", __name__)
TEAM_ROLES = (Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE)


@attachments_bp.get("/documents/<kind>/<int:document_id>/attachments")
@roles_required(*TEAM_ROLES)
def index(kind, document_id):
    return jsonify(list_attachments(kind, document_id, role=current_user.role, **pagination_args(request.args)))


@attachments_bp.post("/documents/<kind>/<int:document_id>/attachments")
@roles_required(*TEAM_ROLES)
def upload(kind, document_id):
    check_role(kind, current_user.role, write=True)
    if request.mimetype != "multipart/form-data":
        return jsonify(message="Incarcarea necesita multipart/form-data."), 415
    request.max_content_length = MAX_FILE_BYTES + 64 * 1024
    request.max_form_memory_size = 128 * 1024
    request.max_form_parts = 5
    if (set(request.form) != {"version", "reason", "upload_key"} or set(request.files) != {"file"}
            or any(len(request.form.getlist(key)) != 1 for key in request.form)
            or len(request.files.getlist("file")) != 1):
        raise ValueError("Trimite un singur file, version, reason si upload_key.")
    raw_version = request.form["version"]
    if not raw_version.isascii() or not raw_version.isdecimal() or len(raw_version) > 10:
        raise ValueError("Versiunea documentului trebuie sa fie un numar intreg pozitiv.")
    result = upload_attachment(actor_user_id=current_user.id, kind=kind, document_id=document_id,
        version=int(raw_version), reason=request.form["reason"], upload_key=request.form["upload_key"], upload=request.files["file"])
    return jsonify(result), 200 if result["replayed"] else 201


@attachments_bp.post("/attachments/<int:attachment_id>/withdraw")
@roles_required(*TEAM_ROLES)
def withdraw(attachment_id):
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 4096
    data = request.get_json()
    if not isinstance(data, dict) or set(data) != {"version", "reason"}:
        raise ValueError("Trimite version si reason.")
    return jsonify(withdraw_attachment(actor_user_id=current_user.id, attachment_id=attachment_id, **data))


@attachments_bp.get("/attachments/<int:attachment_id>/download")
@roles_required(*TEAM_ROLES)
def download(attachment_id):
    data, name, media_type = download_attachment(actor_user_id=current_user.id, attachment_id=attachment_id)
    response = send_file(BytesIO(data), mimetype=media_type, as_attachment=True, download_name=name, etag=False, conditional=False, max_age=0)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response


def error_response(message, status):
    db.session.rollback()
    return jsonify(message=message), status


@attachments_bp.errorhandler(AttachmentForbidden)
def forbidden(error):
    return error_response(str(error), 403)


@attachments_bp.errorhandler(AttachmentNotFound)
def not_found(error):
    return error_response(str(error), 404)


@attachments_bp.errorhandler(AttachmentConflict)
def conflict(error):
    return error_response(str(error), 409)


@attachments_bp.errorhandler(AttachmentTooLarge)
@attachments_bp.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return error_response("Fisierul poate avea cel mult 10 MB; formularul trebuie sa contina un singur fisier si observatii scurte.", 413)


@attachments_bp.errorhandler(BadRequest)
@attachments_bp.errorhandler(ValueError)
def invalid(error):
    return error_response("Cererea nu este valida." if isinstance(error, BadRequest) else str(error), 400)


@attachments_bp.errorhandler(AttachmentStorageError)
def storage_error(error):
    return error_response(str(error), 503)


@attachments_bp.errorhandler(SQLAlchemyError)
def database_error(error):
    return error_response("Operatia nu a putut fi confirmata. Reincarca documentele inainte de o noua incercare.", 503)


@attachments_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response
