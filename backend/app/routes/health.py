from flask import Blueprint
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db


health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    return {"status": "ok"}


@health_bp.get("/ready")
def ready():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM alembic_version LIMIT 1"))
        return {"status": "ready"}, 200, {"Cache-Control": "no-store"}
    except SQLAlchemyError:
        return {"status": "unavailable"}, 503, {"Cache-Control": "no-store"}
