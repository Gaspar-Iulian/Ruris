import pytest

from app.models import Role, User


def make_user(**changes):
    values = {"name": "Ana Popescu", "email": "ana@example.com", "role": Role.PURCHASING}
    values.update(changes)
    return User(**values)


def test_email_and_name_are_normalized():
    user = make_user(name=" Ana Popescu ", email=" ANA@EXAMPLE.COM ")
    assert user.name == "Ana Popescu"
    assert user.email == "ana@example.com"


@pytest.mark.parametrize("email", ["fara-arond", "a@", None])
def test_invalid_email_is_rejected(email):
    with pytest.raises(ValueError):
        make_user(email=email)


@pytest.mark.parametrize("role", ["MANAGER", "admin", None])
def test_unknown_role_is_rejected(role):
    with pytest.raises(ValueError):
        make_user(role=role)


@pytest.mark.parametrize("name", [" ", "a" * 121, None])
def test_invalid_name_is_rejected(name):
    with pytest.raises(ValueError):
        make_user(name=name)


def test_password_hash_uses_salt_and_checks_password():
    first = make_user()
    second = make_user(email="ion@example.com")
    password = "o-parola-pentru-test"
    first.set_password(password)
    second.set_password(password)
    assert first.password_hash != password
    assert first.password_hash != second.password_hash
    assert first.check_password(password)
    assert not first.check_password("parola-incorecta")


def test_password_change_invalidates_previous_password_and_token_version():
    user = make_user()
    user.set_password("prima-parola-de-test")
    old_version = user.token_version
    user.set_password("alta-parola-de-test")
    assert user.token_version == old_version + 1
    assert not user.check_password("prima-parola-de-test")
    assert user.check_password("alta-parola-de-test")


@pytest.mark.parametrize("password", ["scurta", "a" * 73, "\u0103" * 37, None])
def test_invalid_password_is_rejected(password):
    with pytest.raises(ValueError):
        make_user().set_password(password)


def test_password_at_bcrypt_limit_is_not_truncated():
    user = make_user()
    password = "\u0103" * 36
    user.set_password(password)
    assert user.check_password(password)
    assert not user.check_password(password + "x")


def test_invalid_password_does_not_replace_existing_hash():
    user = make_user()
    user.set_password("parola-valida-de-test")
    previous_hash = user.password_hash
    previous_version = user.token_version
    with pytest.raises(ValueError):
        user.set_password("scurta")
    assert user.password_hash == previous_hash
    assert user.token_version == previous_version


def test_unset_password_cannot_authenticate():
    assert not make_user().check_password("parola-valida-de-test")
