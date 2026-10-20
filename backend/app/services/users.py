from sqlalchemy import func, select

from app.extensions import db
from app.models import Role, User
from app.services.audit import record_audit, user_snapshot


class InitialAdminExistsError(ValueError):
    pass


class UserCreationForbiddenError(PermissionError):
    pass


def public_user_data(user):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value}


def list_users(*, page, per_page):
    rows = db.session.execute(
        select(User.id, User.name, User.email, User.role, User.is_active)
        .order_by(User.id).offset((page - 1) * per_page).limit(per_page)
    ).all()
    total = db.session.scalar(select(func.count()).select_from(User))
    return {
        "users": [
            {**public_user_data(row), "is_active": row.is_active} for row in rows
        ],
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }


def create_team_user(*, actor_user_id, name, email, password, role):
    try:
        # Recheck the administrator inside the write transaction.
        actor = db.session.scalar(
            select(User).where(User.id == actor_user_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.role != Role.ADMIN:
            raise UserCreationForbiddenError("Nu ai permisiunea necesara pentru crearea conturilor.")
        if role not in {Role.ACHIZITII.value, Role.DEPOZIT.value, Role.CONTABILITATE.value}:
            raise ValueError("Rolul trebuie sa fie ACHIZITII, DEPOZIT sau CONTABILITATE.")
        user = User(name=name, email=email, role=Role(role), is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        record_audit(
            action="CREATE", entity_type="users", entity_id=user.id,
            actor_user_id=actor.id, after=user_snapshot(user),
        )
        result = {**public_user_data(user), "is_active": user.is_active}
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def create_initial_admin(*, name, email, password):
    with db.session.begin():
        # Allow only one initialization at a time.
        db.session.execute(select(func.pg_advisory_xact_lock(724013)))
        existing_admin = db.session.scalar(select(User.id).where(User.role == Role.ADMIN).limit(1))
        if existing_admin is not None:
            raise InitialAdminExistsError("Exista deja un administrator. Initializarea este blocata.")

        user = User(name=name, email=email, role=Role.ADMIN, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        record_audit(
            action="CREATE",
            entity_type="users",
            entity_id=user.id,
            actor_process="initial_setup",
            after=user_snapshot(user),
        )
    return user
