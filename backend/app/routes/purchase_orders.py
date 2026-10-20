from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.models import Role
from app.permissions import roles_required
from app.services.purchase_orders import OrderCreationForbiddenError, OrderNotFoundError, create_order, get_order, list_orders
from app.services.purchase_orders import OrderConflictError, OrderManagementForbiddenError, edit_order
from app.services.purchase_orders import confirm_order


purchase_orders_bp = Blueprint("purchase_orders", __name__)


@purchase_orders_bp.post("/<int:order_id>/confirm")
@roles_required(Role.ACHIZITII)
def confirm(order_id):
    if not 1 <= order_id <= 9223372036854775807:
        return jsonify(message="Comanda nu a fost gasita."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 4096
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"version"}:
        return jsonify(message="Trimite doar version."), 400
    try:
        order = confirm_order(actor_user_id=current_user.id, order_id=order_id, **data)
    except OrderManagementForbiddenError as error:
        return jsonify(message=str(error)), 403
    except OrderNotFoundError as error:
        return jsonify(message=str(error)), 404
    except OrderConflictError as error:
        return jsonify(message=str(error)), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Comanda nu a putut fi confirmata momentan."), 503
    return jsonify(message="Comanda confirmata.", order=order)


@purchase_orders_bp.patch("/<int:order_id>")
@roles_required(Role.ACHIZITII)
def update(order_id):
    if not 1 <= order_id <= 9223372036854775807:
        return jsonify(message="Comanda nu a fost gasita."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 65536
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"supplier_id", "currency", "items", "version", "reason"}:
        return jsonify(message="Trimite supplier_id, currency, items, version si reason."), 400
    try:
        order = edit_order(actor_user_id=current_user.id, order_id=order_id, **data)
    except OrderManagementForbiddenError as error:
        return jsonify(message=str(error)), 403
    except OrderNotFoundError as error:
        return jsonify(message=str(error)), 404
    except OrderConflictError as error:
        return jsonify(message=str(error)), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Ciorna nu a putut fi modificata momentan."), 503
    return jsonify(message="Ciorna salvata.", order=order)


@purchase_orders_bp.post("")
@roles_required(Role.ACHIZITII)
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
    if not isinstance(data, dict) or set(data) != {"supplier_id", "currency", "items"}:
        return jsonify(message="Trimite doar supplier_id, currency si items."), 400
    try:
        order = create_order(actor_user_id=current_user.id, **data)
    except OrderCreationForbiddenError as error:
        return jsonify(message=str(error)), 403
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Comanda nu a putut fi creata momentan."), 503
    return jsonify(message="Ciorna creata.", order=order), 201


@purchase_orders_bp.get("/<int:order_id>")
@roles_required(Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE)
def detail(order_id):
    if not 1 <= order_id <= 9223372036854775807:
        return jsonify(message="Comanda nu a fost gasita."), 404
    try:
        return jsonify(order=get_order(order_id, role=current_user.role))
    except OrderNotFoundError as error:
        return jsonify(message=str(error)), 404
    except SQLAlchemyError:
        return jsonify(message="Comanda nu este disponibila momentan."), 503


@purchase_orders_bp.get("")
@roles_required(Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE)
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
        return jsonify(list_orders(page=page, per_page=per_page, role=current_user.role))
    except SQLAlchemyError:
        return jsonify(message="Lista comenzilor nu este disponibila momentan."), 503


@purchase_orders_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
