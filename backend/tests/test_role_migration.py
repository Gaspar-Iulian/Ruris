import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import select, text

from app.models import AuditEvent, Role, User


@pytest.mark.parametrize("role", ["PURCHASING", "WAREHOUSE", "ACCOUNTING"])
def test_legacy_role_names_are_not_accepted_for_new_accounts(role):
    with pytest.raises(ValueError):
        User(name="Ana", email="ana@example.com", role=role)


def test_migration_converts_existing_accounts_and_preserves_audit_history(session):
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0004_romanian_roles.py"
    spec = importlib.util.spec_from_file_location("romanian_roles", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = session.connection()
    old_roles = ["ADMIN", "PURCHASING", "WAREHOUSE", "ACCOUNTING"]
    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        identifiers = []
        for index, role in enumerate(old_roles):
            user_id = connection.scalar(text("""
                INSERT INTO users (name, email, password_hash, role, token_version)
                VALUES ('Utilizator test', :email, :password_hash, :role, 3)
                RETURNING id
            """), {"email": f"old-{index}@example.com", "password_hash": "x" * 60, "role": role})
            identifiers.append(user_id)
        connection.execute(AuditEvent.__table__.insert().values(
            actor_process="migration_test", action="CREATE", entity_type="users",
            entity_id=identifiers[1], after_data={"role": "PURCHASING"},
        ))
        migration.upgrade()
        rows = session.execute(select(User.id, User.role, User.token_version).order_by(User.id)).all()
        assert [row.id for row in rows] == identifiers
        assert [row.role for row in rows] == [Role.ADMIN, Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE]
        assert all(row.token_version == 3 for row in rows)
        assert session.scalar(select(AuditEvent.after_data)) == {"role": "PURCHASING"}
        migration.downgrade()
        assert connection.execute(text("SELECT role FROM users ORDER BY id")).scalars().all() == old_roles
