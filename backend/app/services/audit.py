from app.extensions import db
from app.models import AuditEvent, Role


USER_FIELDS = {"name": str, "email": str, "role": str, "is_active": bool}
USER_ACTIONS = {"CREATE", "UPDATE", "PASSWORD_CHANGE", "ACTIVATE", "DEACTIVATE"}


def user_snapshot(user):
    return {
        "name": user.name,
        "email": user.email,
        "role": Role(user.role).value,
        "is_active": user.is_active,
    }


def validate_snapshot(data):
    if data is None:
        return None
    if not isinstance(data, dict) or data.keys() - USER_FIELDS.keys():
        raise ValueError("Auditul contine campuri nepermise.")
    result = {}
    for key, value in data.items():
        if type(value) is not USER_FIELDS[key]:
            raise ValueError("Valoarea unui camp de audit nu este valida.")
        if key == "role":
            value = Role(value).value
        result[key] = value
    return result


def record_audit(*, action, entity_type, entity_id, actor_user_id=None,
                 actor_process=None, before=None, after=None, reason=None):
    if entity_type != "users" or action not in USER_ACTIONS:
        raise ValueError("Operatia de audit nu este configurata.")
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError("Documentul de audit trebuie sa aiba un identificator valid.")
    if (actor_user_id is None) == (actor_process is None):
        raise ValueError("Auditul necesita exact un autor: utilizator sau proces.")
    if actor_user_id is not None and (type(actor_user_id) is not int or actor_user_id <= 0):
        raise ValueError("Utilizatorul autor nu este valid.")
    if actor_process is not None:
        if not isinstance(actor_process, str) or not 1 <= len(actor_process.strip()) <= 80:
            raise ValueError("Procesul autor nu este valid.")
        actor_process = actor_process.strip()
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        reason = reason.strip()

    audit_event = AuditEvent(
        actor_user_id=actor_user_id,
        actor_process=actor_process,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=validate_snapshot(before),
        after_data=validate_snapshot(after),
        reason=reason,
    )
    db.session.add(audit_event)
    return audit_event
