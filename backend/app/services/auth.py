from datetime import datetime, timezone
from uuid import UUID

import bcrypt
from flask_jwt_extended import create_access_token
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import RevokedToken, User
from app.models.user import normalize_email
from app.services.audit import record_audit
from app.services.users import public_user_data


# Unknown accounts still require a password hash check.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-login-password", bcrypt.gensalt(rounds=12))


class AuthenticationError(ValueError):
    pass


class AuthenticationUnavailableError(RuntimeError):
    pass


def user_id_from_claims(claims):
    identity = claims.get("sub")
    version = claims.get("token_version")
    if (
        not isinstance(identity, str) or not 1 <= len(identity) <= 19
        or not identity.isascii() or not identity.isdecimal()
        or type(version) is not int or version < 0
    ):
        return None
    user_id = int(identity)
    if not 1 <= user_id <= 9223372036854775807 or str(user_id) != identity:
        return None
    return user_id


def token_id_from_claims(claims):
    jti = claims.get("jti")
    expiry = claims.get("exp")
    if not isinstance(jti, str) or len(jti) != 36:
        return None
    try:
        token_id = UUID(jti)
    except ValueError:
        return None
    if str(token_id) != jti or type(expiry) is not int or not 0 < expiry <= 253402300799:
        return None
    return token_id


def is_token_revoked(claims):
    token_id = token_id_from_claims(claims)
    if user_id_from_claims(claims) is None or token_id is None:
        return True
    return db.session.scalar(select(RevokedToken.id).where(RevokedToken.token_jti == token_id)) is not None


def get_authenticated_user(claims):
    user_id = user_id_from_claims(claims)
    if user_id is None:
        return None
    user = db.session.scalar(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    if user is None or not user.is_active or user.token_version != claims["token_version"]:
        return None
    return user


def revoke_token(*, user_id, claims):
    try:
        token_id = token_id_from_claims(claims)
        if user_id_from_claims(claims) != user_id or token_id is None:
            raise AuthenticationError("Sesiunea nu este valida.")
        # JWT validation has already opened the transaction.
        revoked_id = db.session.scalar(
            insert(RevokedToken).values(
                user_id=user_id, token_jti=token_id,
                expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
            ).on_conflict_do_nothing(constraint="uq_revoked_tokens_jti").returning(RevokedToken.id)
        )
        if revoked_id is not None:
            record_audit(action="LOGOUT", entity_type="users", entity_id=user_id, actor_user_id=user_id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def authenticate(*, email, password, remote_address):
    result = None
    with db.session.begin():
        try:
            normalized_email = normalize_email(email)
        except ValueError:
            normalized_email = None
        user = db.session.scalar(select(User).where(User.email == normalized_email)) if normalized_email else None

        if user is not None:
            password_valid = user.check_password(password)
        else:
            try:
                encoded = password.encode("utf-8")
            except UnicodeError:
                encoded = b"invalid"
            bcrypt.checkpw(encoded if len(encoded) <= 72 else b"invalid", DUMMY_PASSWORD_HASH)
            password_valid = False

        if user is not None and password_valid and user.is_active:
            token = create_access_token(
                identity=str(user.id), fresh=True,
                additional_claims={"token_version": user.token_version},
            )
            record_audit(action="LOGIN", entity_type="users", entity_id=user.id, actor_user_id=user.id)
            result = (public_user_data(user), token)
        else:
            record_audit(
                action="LOGIN_FAILED", entity_type="authentication", entity_id=1,
                actor_process="authentication",
                after={"email": email.strip().lower(), "remote_address": remote_address},
            )
    if result is None:
        raise AuthenticationError("Email sau parola incorecta.")
    return result
