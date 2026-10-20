from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.models import Role
from app.permissions import roles_required
from app.services.receipts import ReceiptCreationForbiddenError, ReceiptNotFoundError, ReceiptSourceConflictError
from app.services.receipts import create_receipt, get_receipt, list_receipts
from app.services.receipts import ReceiptConflictError, ReceiptManagementForbiddenError, edit_receipt
from app.services.receipts import confirm_receipt


receipts_bp = Blueprint("receipts", __name__)


@receipts_bp.post("/<int:receipt_id>/confirm")
@roles_required(Role.DEPOZIT)
def confirm(receipt_id):
    if not 1 <= receipt_id <= 9223372036854775807:
        return jsonify(message="Receptia nu a fost gasita."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 65536
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"version", "reason", "items"}:
        return jsonify(message="Trimite version, reason si items."), 400
    try:
        receipt = confirm_receipt(actor_user_id=current_user.id, receipt_id=receipt_id, **data)
    except ReceiptManagementForbiddenError as error:
        return jsonify(message=str(error)), 403
    except ReceiptNotFoundError as error:
        return jsonify(message=str(error)), 404
    except ReceiptConflictError as error:
        return jsonify(message=str(error)), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Receptia nu a putut fi confirmata momentan."), 503
    return jsonify(message="Receptia a fost confirmata.", receipt=receipt)


@receipts_bp.patch("/<int:receipt_id>")
@roles_required(Role.DEPOZIT)
def update(receipt_id):
    if not 1 <= receipt_id <= 9223372036854775807:
        return jsonify(message="Receptia nu a fost gasita."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 65536
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"version", "reason", "delivery_reference", "received_at", "items"}:
        return jsonify(message="Trimite version, reason, delivery_reference, received_at si items."), 400
    try:
        receipt = edit_receipt(actor_user_id=current_user.id, receipt_id=receipt_id, **data)
    except ReceiptManagementForbiddenError as error:
        return jsonify(message=str(error)), 403
    except ReceiptNotFoundError as error:
        return jsonify(message=str(error)), 404
    except ReceiptConflictError as error:
        return jsonify(message=str(error)), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Ciorna receptiei nu a putut fi modificata momentan."), 503
    return jsonify(message="Ciorna receptiei a fost salvata.", receipt=receipt)


@receipts_bp.post("")
@roles_required(Role.DEPOZIT)
def create():
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 65536
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"purchase_order_id", "delivery_reference", "received_at", "items"}:
        return jsonify(message="Trimite purchase_order_id, delivery_reference, received_at si items."), 400
    try:
        receipt = create_receipt(actor_user_id=current_user.id, **data)
    except ReceiptCreationForbiddenError as error:
        return jsonify(message=str(error)), 403
    except ReceiptNotFoundError as error:
        return jsonify(message=str(error)), 404
    except ReceiptSourceConflictError as error:
        return jsonify(message=str(error)), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Receptia nu a putut fi creata momentan."), 503
    return jsonify(message="Ciorna receptiei a fost creata.", receipt=receipt), 201


@receipts_bp.get("/<int:receipt_id>")
@roles_required(Role.DEPOZIT, Role.ACHIZITII, Role.CONTABILITATE)
def detail(receipt_id):
    if not 1 <= receipt_id <= 9223372036854775807:
        return jsonify(message="Receptia nu a fost gasita."), 404
    try:
        return jsonify(receipt=get_receipt(receipt_id, role=current_user.role))
    except ReceiptNotFoundError as error:
        return jsonify(message=str(error)), 404
    except SQLAlchemyError:
        return jsonify(message="Receptia nu este disponibila momentan."), 503


@receipts_bp.get("")
@roles_required(Role.DEPOZIT, Role.ACHIZITII, Role.CONTABILITATE)
def index():
    if set(request.args) - {"page", "per_page"} or any(len(request.args.getlist(key)) != 1 for key in request.args):
        return jsonify(message="Parametrii permisi sunt page si per_page, o singura data fiecare."), 400
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        return jsonify(message="Paginarea trebuie sa contina numere intregi."), 400
    if not 1 <= page <= 1000000 or not 1 <= per_page <= 100:
        return jsonify(message="Paginare invalida: page 1-1000000, per_page 1-100."), 400
    try:
        return jsonify(list_receipts(page=page, per_page=per_page, role=current_user.role))
    except SQLAlchemyError:
        return jsonify(message="Lista receptiilor nu este disponibila momentan."), 503


@receipts_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
