from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user, get_jwt, jwt_required, set_access_cookies, unset_jwt_cookies
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.extensions import limiter
from app.services.auth import AuthenticationError, authenticate, revoke_token
from app.services.users import public_user_data


auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/me")
@jwt_required()
def me():
    return jsonify(user=public_user_data(current_user))


@auth_bp.post("/logout")
@jwt_required()
def logout():
    try:
        revoke_token(user_id=current_user.id, claims=get_jwt())
    except AuthenticationError as error:
        return jsonify(message=str(error)), 401
    except SQLAlchemyError:
        return jsonify(message="Deconectarea nu este disponibila momentan."), 503
    response = jsonify(message="Deconectare reusita.")
    unset_jwt_cookies(response)
    return response


@auth_bp.post("/login")
@limiter.limit("10 per minute", deduct_when=lambda response: response.status_code == 401)
def login():
    origin = request.headers.get("Origin")
    if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
        origin is not None and origin != request.host_url.rstrip("/")
    ):
        return jsonify(message="Originea cererii nu este permisa."), 403
    if not request.is_json:
        return jsonify(message="Cererea trebuie sa contina JSON."), 415
    request.max_content_length = 4096
    try:
        data = request.get_json()
    except RequestEntityTooLarge:
        return jsonify(message="Cererea este prea mare."), 413
    except BadRequest:
        return jsonify(message="Corpul cererii nu este JSON valid."), 400
    if not isinstance(data, dict) or set(data) != {"email", "password"}:
        return jsonify(message="Trimite doar email si password."), 400
    if (
        not isinstance(data["email"], str) or not 1 <= len(data["email"].strip()) <= 254
        or not isinstance(data["password"], str) or not data["password"]
    ):
        return jsonify(message="Emailul si parola sunt obligatorii si trebuie sa fie texte."), 400
    try:
        user, token = authenticate(
            email=data["email"], password=data["password"],
            remote_address=request.remote_addr or "unknown",
        )
    except AuthenticationError as error:
        return jsonify(message=str(error)), 401
    except SQLAlchemyError:
        return jsonify(message="Autentificarea nu este disponibila momentan."), 503
    response = jsonify(message="Autentificare reusita.", user=user)
    set_access_cookies(response, token)
    return response


@auth_bp.errorhandler(429)
def rate_limit_exceeded(error):
    return jsonify(message="Prea multe incercari. Reincearca peste un minut."), 429


@auth_bp.after_request
def prevent_auth_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response
