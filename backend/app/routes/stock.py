from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Product, Role, StockMovement
from app.permissions import roles_required


stock_bp = Blueprint("stock", __name__)


@stock_bp.get("")
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
        balances = select(StockMovement.product_id, func.sum(StockMovement.quantity_delta).label("quantity")).group_by(StockMovement.product_id).subquery()
        rows = db.session.execute(select(Product.id, Product.sku, Product.name, Product.unit, Product.is_active,
                                          func.coalesce(balances.c.quantity, 0).label("quantity"))
                                   .outerjoin(balances, balances.c.product_id == Product.id).order_by(Product.id)
                                   .offset((page - 1) * per_page).limit(per_page))
        return jsonify(stock=[{**dict(row._mapping), "quantity": format(row.quantity, ".3f")} for row in rows],
                       page=page, per_page=per_page, total=db.session.scalar(select(func.count()).select_from(Product)))
    except SQLAlchemyError:
        return jsonify(message="Stocul nu este disponibil momentan."), 503


@stock_bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
