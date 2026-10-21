from flask import Flask

from app.cli import create_admin_command, preview_overdue_emails_command
from app.cli import send_overdue_emails_local_command, send_test_email_command
from app.cli import list_email_deliveries_command
from app.cli import run_notification_worker_command
from app.cli import preview_blocked_invoice_emails_command, send_blocked_invoice_emails_local_command
from app.cli import preview_receipt_emails_command, send_notification_emails_command
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
from app.routes.receipts import receipts_bp
from app.routes.stock import stock_bp
from app.routes.invoices import invoices_bp
from app.routes.notifications import notifications_bp
from app.routes.attachments import attachments_bp
from app.cli import check_attachments_command


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
    app.register_blueprint(receipts_bp, url_prefix="/api/receipts")
    app.register_blueprint(stock_bp, url_prefix="/api/stock")
    app.register_blueprint(invoices_bp, url_prefix="/api/invoices")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(attachments_bp, url_prefix="/api")
    app.cli.add_command(create_admin_command)
    app.cli.add_command(preview_overdue_emails_command)
    app.cli.add_command(send_test_email_command)
    app.cli.add_command(send_overdue_emails_local_command)
    app.cli.add_command(list_email_deliveries_command)
    app.cli.add_command(run_notification_worker_command)
    app.cli.add_command(preview_blocked_invoice_emails_command)
    app.cli.add_command(send_blocked_invoice_emails_local_command)
    app.cli.add_command(preview_receipt_emails_command)
    app.cli.add_command(send_notification_emails_command)
    app.cli.add_command(check_attachments_command)
    return app
