from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.models import Role
from app.permissions import roles_required
from app.services.suppliers import SupplierCreationForbiddenError, create_supplier, list_suppliers
from app.services.suppliers import SupplierManagementForbiddenError, SupplierNotFoundError, change_supplier


suppliers_bp = Blueprint("suppliers", __name__)


@suppliers_bp.patch("/<int:supplier_id>")
@suppliers_bp.patch("/<int:supplier_id>/status")
@roles_required(Role.ACHIZITII)
def update(supplier_id):
    if not 1 <= supplier_id <= 9223372036854775807:
        return jsonify(message="Furnizorul nu a fost gasit."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 4096
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    status_change = request.path.endswith("/status")
    allowed = {"is_active", "reason"} if status_change else {"name", "email", "reason"}
    if (not isinstance(data, dict) or "reason" not in data or data.keys() - allowed
            or not data.keys() - {"reason"} or status_change and "is_active" not in data):
        return jsonify(message="Trimite campurile permise si un motiv obligatoriu."), 400
    try:
        supplier = change_supplier(actor_user_id=current_user.id, supplier_id=supplier_id,
                                   reason=data["reason"], changes={key: value for key, value in data.items() if key != "reason"})
    except SupplierManagementForbiddenError as error:
        return jsonify(message=str(error)), 403
    except SupplierNotFoundError as error:
        return jsonify(message=str(error)), 404
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Furnizorul nu a putut fi modificat momentan."), 503
    return jsonify(message="Furnizor salvat.", supplier=supplier)


@suppliers_bp.post("")
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
    required = {"name", "tax_country", "tax_id"}
    if not isinstance(data, dict) or not required <= data.keys() or data.keys() - required - {"email"}:
        return jsonify(message="Trimite name, tax_country, tax_id si optional email."), 400
    try:
        supplier = create_supplier(actor_user_id=current_user.id, **data)
    except SupplierCreationForbiddenError as error:
        return jsonify(message=str(error)), 403
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_suppliers_tax_identity":
            return jsonify(message="Exista deja un furnizor cu acest cod fiscal in tara selectata."), 409
        return jsonify(message="Furnizorul nu a putut fi creat momentan."), 503
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Furnizorul nu a putut fi creat momentan."), 503
    return jsonify(message="Furnizor creat.", supplier=supplier), 201


@suppliers_bp.get("")
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
        return jsonify(list_suppliers(role=current_user.role, page=page, per_page=per_page))
    except SQLAlchemyError:
        return jsonify(message="Lista furnizorilor nu este disponibila momentan."), 503


@suppliers_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
