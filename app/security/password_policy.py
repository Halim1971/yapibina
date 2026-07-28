class PasswordPolicyError(ValueError):
    pass


class PasswordTooShortError(PasswordPolicyError):
    pass


class PasswordMissingLetterError(PasswordPolicyError):
    pass


class PasswordMissingDigitError(PasswordPolicyError):
    pass


class PasswordMatchesEmailError(PasswordPolicyError):
    pass


def validate_password(password: str, *, email: str | None = None) -> None:
    if not password or not password.strip() or len(password) < 10:
        raise PasswordTooShortError("Password must contain at least 10 characters.")
    if email is not None and password.casefold() == email.strip().casefold():
        raise PasswordMatchesEmailError("Password cannot be the email address.")
    if not any(character.isalpha() for character in password):
        raise PasswordMissingLetterError("Password must contain at least one letter.")
    if not any(character.isdigit() for character in password):
        raise PasswordMissingDigitError("Password must contain at least one digit.")
