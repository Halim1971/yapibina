from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email

from app.models.base import normalize_email


def _normalize_email_filter(value: str | None) -> str:
    if value is None:
        return ""
    try:
        return normalize_email(value)
    except ValueError:
        return value.strip().lower()


class LoginForm(FlaskForm):  # type: ignore[misc]
    email = EmailField(
        "E-posta",
        validators=[
            DataRequired(message="E-posta adresi zorunludur."),
            Email(message="Geçerli bir e-posta adresi girin."),
        ],
        filters=[_normalize_email_filter],
    )
    password = PasswordField(
        "Parola",
        validators=[DataRequired(message="Parola zorunludur.")],
    )
    remember_me = BooleanField("Beni hatırla")
    submit = SubmitField("Giriş yap")
