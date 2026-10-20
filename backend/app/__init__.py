from flask import Flask

from app.config import get_config
from app.extensions import db, migrate
from app.models import User
from app.routes.health import health_bp


def create_app():
    app = Flask(__name__)
    app.config.update(get_config())
    db.init_app(app)
    migrate.init_app(app, db)
    app.register_blueprint(health_bp, url_prefix="/api")
    return app
