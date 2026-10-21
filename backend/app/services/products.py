from sqlalchemy import func, select

from app.extensions import db
from app.models import Product, Role, User
from app.services.audit import record_audit


class ProductCreationForbiddenError(PermissionError):
    pass


class ProductManagementForbiddenError(PermissionError):
    pass


class ProductNotFoundError(LookupError):
    pass


def change_product(*, actor_user_id, product_id, reason, changes):
    try:
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        if not isinstance(changes, dict) or set(changes) not in ({"name"}, {"is_active"}):
            raise ValueError("Modifica numele sau separat starea produsului.")
        if "is_active" in changes and type(changes["is_active"]) is not bool:
            raise ValueError("Starea trebuie sa fie true sau false.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise ProductManagementForbiddenError("Doar achizitiile pot modifica produse.")
        product = db.session.scalar(select(Product).where(Product.id == product_id).with_for_update().execution_options(populate_existing=True))
        if product is None:
            raise ProductNotFoundError("Produsul nu a fost gasit.")
        before = {key: value for key, value in product_data(product).items() if key != "id"}
        for key, value in changes.items():
            setattr(product, key, value)
        result = product_data(product)
        after = {key: value for key, value in result.items() if key != "id"}
        if before != after:
            action = "UPDATE"
            if "is_active" in changes:
                action = "ACTIVATE" if product.is_active else "DEACTIVATE"
            record_audit(action=action, entity_type="products", entity_id=product.id,
                         actor_user_id=actor.id, before=before, after=after, reason=reason.strip())
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def product_data(product):
    return {key: getattr(product, key) for key in ("id", "sku", "name", "unit", "is_active")}


def create_product(*, actor_user_id, sku, name, unit):
    try:
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise ProductCreationForbiddenError("Doar achizitiile pot crea produse.")
        product = Product(sku=sku, name=name, unit=unit)
        db.session.add(product)
        db.session.flush()
        result = product_data(product)
        record_audit(action="CREATE", entity_type="products", entity_id=product.id,
                     actor_user_id=actor.id, after={key: value for key, value in result.items() if key != "id"})
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def list_products(*, page, per_page):
    rows = db.session.execute(select(Product.id, Product.sku, Product.name, Product.unit, Product.is_active)
                              .order_by(Product.is_active.desc(), Product.id).offset((page - 1) * per_page).limit(per_page))
    return {"products": [dict(row._mapping) for row in rows], "page": page, "per_page": per_page,
            "total": db.session.scalar(select(func.count()).select_from(Product))}
