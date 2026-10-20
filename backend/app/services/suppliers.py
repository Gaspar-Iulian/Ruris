from sqlalchemy import func, select

from app.extensions import db
from app.models import Role, User
from app.models.supplier import Supplier, normalize_tax_identity
from app.services.audit import record_audit


class SupplierCreationForbiddenError(PermissionError):
    pass


class SupplierManagementForbiddenError(PermissionError):
    pass


class SupplierNotFoundError(LookupError):
    pass


def change_supplier(*, actor_user_id, supplier_id, reason, changes):
    try:
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        if not isinstance(changes, dict) or not changes or not (
            set(changes) <= {"name", "email"} or set(changes) == {"is_active"}
        ):
            raise ValueError("Modifica numele/emailul sau separat starea furnizorului.")
        if "is_active" in changes and type(changes["is_active"]) is not bool:
            raise ValueError("Starea trebuie sa fie true sau false.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise SupplierManagementForbiddenError("Doar achizitiile pot modifica furnizori.")
        supplier = db.session.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update().execution_options(populate_existing=True))
        if supplier is None:
            raise SupplierNotFoundError("Furnizorul nu a fost gasit.")
        before = {key: value for key, value in supplier_data(supplier).items() if key != "id"}
        for key, value in changes.items():
            setattr(supplier, key, value)
        result = supplier_data(supplier)
        after = {key: value for key, value in result.items() if key != "id"}
        if before != after:
            action = "UPDATE"
            if "is_active" in changes:
                action = "ACTIVATE" if supplier.is_active else "DEACTIVATE"
            record_audit(action=action, entity_type="suppliers", entity_id=supplier.id,
                         actor_user_id=actor.id, before=before, after=after, reason=reason.strip())
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def supplier_data(supplier):
    return {key: getattr(supplier, key) for key in (
        "id", "name", "tax_country", "tax_id", "email", "is_active",
    )}


def create_supplier(*, actor_user_id, name, tax_country, tax_id, email=None):
    try:
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise SupplierCreationForbiddenError("Doar achizitiile pot crea furnizori.")
        tax_country, tax_id = normalize_tax_identity(tax_country, tax_id)
        supplier = Supplier(name=name, tax_country=tax_country, tax_id=tax_id, email=email)
        db.session.add(supplier)
        db.session.flush()
        result = supplier_data(supplier)
        record_audit(action="CREATE", entity_type="suppliers", entity_id=supplier.id,
                     actor_user_id=actor.id, after={key: value for key, value in result.items() if key != "id"})
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def list_suppliers(*, role, page, per_page):
    fields = [Supplier.id, Supplier.name, Supplier.is_active]
    if role in (Role.ACHIZITII, Role.CONTABILITATE):
        fields.extend([Supplier.tax_country, Supplier.tax_id, Supplier.email])
    rows = db.session.execute(select(*fields).order_by(Supplier.id).offset((page - 1) * per_page).limit(per_page))
    return {"suppliers": [dict(row._mapping) for row in rows], "page": page, "per_page": per_page,
            "total": db.session.scalar(select(func.count()).select_from(Supplier))}
