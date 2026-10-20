from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import jwt
from app.services import auth


def authentication_error(message, status=401):
    response = jsonify(message=message)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def register_jwt_callbacks(app):
    @jwt.token_in_blocklist_loader
    def check_revocation(jwt_header, jwt_data):
        try:
            return auth.is_token_revoked(jwt_data)
        except SQLAlchemyError:
            raise auth.AuthenticationUnavailableError() from None

    @jwt.revoked_token_loader
    def revoked_token(jwt_header, jwt_data):
        return authentication_error("Sesiunea a fost inchisa. Autentifica-te din nou.")

    @jwt.user_lookup_loader
    def load_user(jwt_header, jwt_data):
        try:
            return auth.get_authenticated_user(jwt_data)
        except SQLAlchemyError:
            raise auth.AuthenticationUnavailableError() from None

    @jwt.user_lookup_error_loader
    def user_lookup_failed(jwt_header, jwt_data):
        return authentication_error("Sesiunea nu mai este valida. Autentifica-te din nou.")

    @jwt.unauthorized_loader
    def token_missing_or_csrf_invalid(reason):
        return authentication_error("Autentificare necesara sau cerere invalida.")

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return authentication_error("Token de autentificare invalid.")

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_data):
        return authentication_error("Sesiunea a expirat. Autentifica-te din nou.")

    @app.errorhandler(auth.AuthenticationUnavailableError)
    def authentication_unavailable(error):
        return authentication_error("Verificarea sesiunii nu este disponibila momentan.", 503)
