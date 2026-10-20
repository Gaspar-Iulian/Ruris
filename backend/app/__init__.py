from flask import Flask

from app.cli import create_admin_command
from app.config import get_config
from app.extensions import db, jwt, limiter, migrate
from app.jwt_callbacks import register_jwt_callbacks
from app.models import User
from app.routes.health import health_bp
from app.routes.auth import auth_bp
from app.routes.users import users_bp
from app.routes.suppliers import suppliers_bp
from app.routes.products import products_bp
from app.routes.purchase_orders import purchase_orders_bp


def create_app():
    app = Flask(__name__)
    app.config.update(get_config())
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    register_jwt_callbacks(app)
    limiter.init_app(app)
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(suppliers_bp, url_prefix="/api/suppliers")
    app.register_blueprint(products_bp, url_prefix="/api/products")
    app.register_blueprint(purchase_orders_bp, url_prefix="/api/purchase-orders")
    app.cli.add_command(create_admin_command)
    return app
