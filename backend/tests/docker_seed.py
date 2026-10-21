from sqlalchemy import func, select

from app import create_app
from app.extensions import db
from app.models import Role, User
from app.services.users import create_initial_admin, create_team_user


app = create_app()
with app.app_context():
    if app.config["SQLALCHEMY_DATABASE_URI"].database != "ruris_delivery":
        raise RuntimeError("Docker smoke seed requires the isolated ruris_delivery database.")
    if db.session.scalar(select(func.count()).select_from(User)):
        raise RuntimeError("Docker smoke seed requires an empty user table.")
    db.session.rollback()
    admin = create_initial_admin(name="Docker smoke admin", email="admin@browser.example.com", password="Browser-test-2026!")
    for role in (Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE):
        create_team_user(actor_user_id=admin.id, name=f"Docker {role.value}", email=f"{role.value.lower()}@browser.example.com",
                         password="Browser-test-2026!", role=role.value)
    print("Isolated Docker smoke accounts created.")
