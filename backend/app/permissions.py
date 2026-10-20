from functools import wraps

from flask import jsonify
from flask_jwt_extended import current_user, jwt_required

from app.models import Role


def roles_required(*roles):
    if not roles:
        raise ValueError("Trebuie declarat cel putin un rol permis.")
    allowed_roles = frozenset(Role(role) for role in roles)

    def decorate(view):
        @wraps(view)
        @jwt_required()
        def protected_view(*args, **kwargs):
            if current_user.role not in allowed_roles:
                response = jsonify(message="Nu ai permisiunea necesara pentru aceasta operatie.")
                response.status_code = 403
                response.headers["Cache-Control"] = "no-store"
                return response
            return view(*args, **kwargs)

        return protected_view

    return decorate
