from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.models import Role
from app.permissions import roles_required
from app.services.products import ProductCreationForbiddenError, create_product, list_products
from app.services.products import ProductManagementForbiddenError, ProductNotFoundError, change_product


products_bp = Blueprint("products", __name__)


@products_bp.patch("/<int:product_id>")
@products_bp.patch("/<int:product_id>/status")
@roles_required(Role.ACHIZITII)
def update(product_id):
    if not 1 <= product_id <= 9223372036854775807:
        return jsonify(message="Produsul nu a fost gasit."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 4096
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    field = "is_active" if request.path.endswith("/status") else "name"
    if not isinstance(data, dict) or set(data) != {field, "reason"}:
        return jsonify(message="Trimite doar campul permis si un motiv obligatoriu."), 400
    try:
        product = change_product(actor_user_id=current_user.id, product_id=product_id,
                                 reason=data["reason"], changes={field: data[field]})
    except ProductManagementForbiddenError as error:
        return jsonify(message=str(error)), 403
    except ProductNotFoundError as error:
        return jsonify(message=str(error)), 404
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Produsul nu a putut fi modificat momentan."), 503
    return jsonify(message="Produs salvat.", product=product)


@products_bp.post("")
@roles_required(Role.ACHIZITII)
def create():
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 4096
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"sku", "name", "unit"}:
        return jsonify(message="Trimite doar sku, name si unit."), 400
    try:
        product = create_product(actor_user_id=current_user.id, **data)
    except ProductCreationForbiddenError as error:
        return jsonify(message=str(error)), 403
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_products_sku":
            return jsonify(message="Exista deja un produs cu acest cod."), 409
        return jsonify(message="Produsul nu a putut fi creat momentan."), 503
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Produsul nu a putut fi creat momentan."), 503
    return jsonify(message="Produs creat.", product=product), 201


@products_bp.get("")
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
        return jsonify(list_products(page=page, per_page=per_page))
    except SQLAlchemyError:
        return jsonify(message="Lista produselor nu este disponibila momentan."), 503


@products_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
