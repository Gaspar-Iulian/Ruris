from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.models import Role
from app.permissions import roles_required
from app.services.users import UserCreationForbiddenError, create_team_user, list_users


users_bp = Blueprint("users", __name__)


@users_bp.post("")
@roles_required(Role.ADMIN)
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
    if not isinstance(data, dict) or set(data) != {"name", "email", "password", "role"}:
        return jsonify(message="Trimite doar name, email, password si role."), 400
    if not all(isinstance(value, str) for value in data.values()):
        return jsonify(message="Numele, emailul, parola si rolul trebuie sa fie texte."), 400
    try:
        user = create_team_user(actor_user_id=current_user.id, **data)
    except UserCreationForbiddenError as error:
        return jsonify(message=str(error)), 403
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_users_email":
            return jsonify(message="Emailul este deja folosit de un cont."), 409
        return jsonify(message="Contul nu a putut fi creat momentan."), 503
    except ValueError as error:
        return jsonify(message=str(error)), 400
    except SQLAlchemyError:
        return jsonify(message="Contul nu a putut fi creat momentan."), 503
    return jsonify(message="Cont creat.", user=user), 201


@users_bp.get("")
@roles_required(Role.ADMIN)
def index():
    if set(request.args) - {"page", "per_page"} or any(
        len(request.args.getlist(key)) != 1 for key in request.args
    ):
        return jsonify(message="Parametrii permisi sunt page si per_page, o singura data fiecare."), 400
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        return jsonify(message="Parametrii de paginare trebuie sa fie numere intregi."), 400
    if not 1 <= page <= 1000000 or not 1 <= per_page <= 100:
        return jsonify(message="page trebuie sa fie intre 1 si 1000000, iar per_page intre 1 si 100."), 400
    try:
        return jsonify(list_users(page=page, per_page=per_page))
    except SQLAlchemyError:
        return jsonify(message="Lista utilizatorilor nu este disponibila momentan."), 503


@users_bp.after_request
def prevent_user_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
