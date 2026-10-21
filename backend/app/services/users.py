from sqlalchemy import func, select

from app.extensions import db
from app.models import Role, User
from app.services.audit import record_audit, user_snapshot


ADMIN_WRITE_LOCK_ID = 724013


class InitialAdminExistsError(ValueError):
    pass


class UserCreationForbiddenError(PermissionError):
    pass


class UserManagementForbiddenError(PermissionError):
    pass


class UserNotFoundError(LookupError):
    pass


class LastActiveAdminError(ValueError):
    pass


def _lock_managed_user(actor_user_id, user_id):
    # Share the lock with status changes and initial setup.
    db.session.execute(select(func.pg_advisory_xact_lock(ADMIN_WRITE_LOCK_ID)))
    actor = db.session.scalar(
        select(User).where(User.id == actor_user_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or not actor.is_active or actor.role != Role.ADMIN:
        raise UserManagementForbiddenError("Nu ai permisiunea necesara pentru modificarea conturilor.")
    user = db.session.scalar(
        select(User).where(User.id == user_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise UserNotFoundError("Contul nu a fost gasit.")
    return actor, user


def _require_another_active_admin(user):
    if user.role == Role.ADMIN and user.is_active:
        active_admins = db.session.scalar(
            select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active.is_(True))
        )
        if active_admins <= 1:
            raise LastActiveAdminError("Ultimul administrator activ nu poate pierde drepturile de administrare.")


def public_user_data(user):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value}


def list_users(*, page, per_page):
    rows = db.session.execute(
        select(User.id, User.name, User.email, User.role, User.is_active)
        .order_by(User.is_active.desc(), User.id).offset((page - 1) * per_page).limit(per_page)
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


def set_user_active(*, actor_user_id, user_id, is_active, reason):
    try:
        if type(is_active) is not bool:
            raise ValueError("is_active trebuie sa fie true sau false.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        actor, user = _lock_managed_user(actor_user_id, user_id)
        if user.is_active != is_active:
            if not is_active:
                _require_another_active_admin(user)
            before = user_snapshot(user)
            user.is_active = is_active
            user.token_version += 1
            record_audit(
                action="ACTIVATE" if is_active else "DEACTIVATE",
                entity_type="users", entity_id=user.id, actor_user_id=actor.id,
                before=before, after=user_snapshot(user), reason=reason.strip(),
            )
        result = {**public_user_data(user), "is_active": user.is_active}
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def set_user_role(*, actor_user_id, user_id, role, reason):
    try:
        try:
            selected_role = Role(role)
        except (TypeError, ValueError):
            raise ValueError("Rolul trebuie sa fie ADMIN, ACHIZITII, DEPOZIT sau CONTABILITATE.") from None
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        actor, user = _lock_managed_user(actor_user_id, user_id)
        if user.role != selected_role:
            if selected_role != Role.ADMIN:
                _require_another_active_admin(user)
            before = user_snapshot(user)
            user.role = selected_role
            user.token_version += 1
            record_audit(
                action="ROLE_CHANGE", entity_type="users", entity_id=user.id,
                actor_user_id=actor.id, before=before, after=user_snapshot(user), reason=reason.strip(),
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
        db.session.execute(select(func.pg_advisory_xact_lock(ADMIN_WRITE_LOCK_ID)))
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
