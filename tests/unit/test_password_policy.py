import pytest

from app.models import User
from app.security.password_policy import (
    PasswordMatchesEmailError,
    PasswordMissingDigitError,
    PasswordMissingLetterError,
    PasswordTooShortError,
)


def user() -> User:
    return User(
        email="person@example.com",
        password_hash="pending",
        first_name="Test",
        last_name="Person",
    )


def test_password_is_stored_as_hash() -> None:
    account = user()
    account.set_password("ValidPassword123")

    assert account.password_hash != "ValidPassword123"
    assert account.check_password("ValidPassword123")


@pytest.mark.parametrize(
    ("password", "error_type"),
    [
        ("Short1", PasswordTooShortError),
        ("1234567890", PasswordMissingLetterError),
        ("abcdefghij", PasswordMissingDigitError),
    ],
)
def test_password_policy_rejects_invalid_values(
    password: str,
    error_type: type[ValueError],
) -> None:
    with pytest.raises(error_type):
        user().set_password(password)


def test_password_cannot_equal_email() -> None:
    account = user()

    with pytest.raises(PasswordMatchesEmailError):
        account.set_password("person@example.com")
