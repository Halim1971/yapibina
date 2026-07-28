import uuid

import pytest

from app.extensions import db
from app.models import User, UserStatus
from app.models.user import load_user

VALID_PASSWORD = "correct horse battery staple 1"


def make_user(email: str = "USER@Example.COM") -> User:
    user = User(
        email=email,
        password_hash="not-yet-set",
        first_name="Test",
        last_name="User",
    )
    user.set_password(VALID_PASSWORD)
    return user


def test_email_is_normalized() -> None:
    user = make_user("  USER@Example.COM ")

    assert user.email == "user@example.com"


def test_password_is_hashed_and_verified() -> None:
    user = make_user()

    assert user.password_hash != VALID_PASSWORD
    assert user.check_password(VALID_PASSWORD) is True
    assert user.check_password("wrong password") is False


def test_blank_password_is_rejected() -> None:
    user = make_user()

    with pytest.raises(ValueError, match="at least"):
        user.set_password("   ")


def test_inactive_user_is_not_active() -> None:
    user = make_user()
    user.status = UserStatus.INACTIVE

    assert user.is_active is False


def test_user_loader_handles_invalid_and_missing_uuid(app: object) -> None:
    del app

    assert load_user("not-a-uuid") is None
    assert load_user(str(uuid.uuid4())) is None


def test_user_loader_finds_user(app: object) -> None:
    del app
    user = make_user()
    db.session.add(user)
    db.session.commit()

    loaded = load_user(str(user.id))

    assert loaded is not None
    assert loaded.id == user.id
