from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.models import Role
from app.permissions import roles_required
from app.services.invoices import InvoiceForbiddenError, InvoiceNotFoundError, create_invoice, get_invoice, list_invoices
from app.services.invoices import InvoiceConflictError, update_invoice


invoices_bp = Blueprint("invoices", __name__)


@invoices_bp.patch("/<int:invoice_id>")
@roles_required(Role.CONTABILITATE)
def update(invoice_id):
    if not 1 <= invoice_id <= 9223372036854775807:
        return jsonify(message="Factura nu a fost gasita."), 404
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 65536
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"version", "reason", "supplier_id", "series", "number", "invoice_date", "due_date", "currency", "items"}:
        return jsonify(message="Trimite toate campurile ciornei, version si reason."), 400
    try:
        invoice = update_invoice(actor_user_id=current_user.id, invoice_id=invoice_id, **data)
    except InvoiceForbiddenError as error:
        return jsonify(message=str(error)), 403
    except InvoiceNotFoundError as error:
        return jsonify(message=str(error)), 404
    except InvoiceConflictError as error:
        return jsonify(message=str(error)), 409
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_invoices_supplier_reference":
            return jsonify(message="Factura exista deja pentru acest furnizor, serie si numar."), 409
        return jsonify(message="Factura nu a putut fi salvata momentan."), 503
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Factura nu a putut fi salvata momentan."), 503
    return jsonify(message="Ciorna facturii a fost salvata.", invoice=invoice)


@invoices_bp.post("")
@roles_required(Role.CONTABILITATE)
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
    if not isinstance(data, dict) or set(data) != {"supplier_id", "series", "number", "invoice_date", "due_date", "currency", "items"}:
        return jsonify(message="Trimite supplier_id, series, number, invoice_date, due_date, currency si items."), 400
    try:
        invoice = create_invoice(actor_user_id=current_user.id, **data)
    except InvoiceForbiddenError as error:
        return jsonify(message=str(error)), 403
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_invoices_supplier_reference":
            return jsonify(message="Factura exista deja pentru acest furnizor, serie si numar."), 409
        return jsonify(message="Factura nu a putut fi salvata momentan."), 503
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Factura nu a putut fi salvata momentan."), 503
    return jsonify(message="Ciorna facturii a fost creata.", invoice=invoice), 201


@invoices_bp.get("")
@roles_required(Role.CONTABILITATE)
def index():
    if set(request.args) - {"page", "per_page"} or any(len(request.args.getlist(key)) != 1 for key in request.args):
        return jsonify(message="Parametrii permisi sunt page si per_page, o singura data fiecare."), 400
    try:
        page, per_page = int(request.args.get("page", "1")), int(request.args.get("per_page", "20"))
        if not 1 <= page <= 1000000 or not 1 <= per_page <= 100:
            raise ValueError()
        return jsonify(list_invoices(page=page, per_page=per_page))
    except ValueError:
        return jsonify(message="Paginare invalida: page 1-1000000, per_page 1-100."), 400
    except SQLAlchemyError:
        return jsonify(message="Lista facturilor nu este disponibila momentan."), 503


@invoices_bp.get("/<int:invoice_id>")
@roles_required(Role.CONTABILITATE)
def detail(invoice_id):
    try:
        return jsonify(invoice=get_invoice(invoice_id))
    except (InvoiceNotFoundError, ValueError):
        return jsonify(message="Factura nu a fost gasita."), 404
    except SQLAlchemyError:
        return jsonify(message="Factura nu este disponibila momentan."), 503


@invoices_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
