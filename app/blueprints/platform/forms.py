from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import Email, InputRequired, Length, Optional, Regexp

from app.models import DomainType, OrganizationStatus

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class OrganizationForm(FlaskForm):  # type: ignore[misc]
    name = StringField("Firma adı", validators=[InputRequired(), Length(max=160)])
    legal_name = StringField("Ticari unvan", validators=[Optional(), Length(max=240)])
    slug = StringField("Slug", validators=[InputRequired(), Length(max=100)])
    support_email = EmailField(
        "Destek e-postası", validators=[Optional(), Email(), Length(max=254)]
    )
    phone = StringField("Telefon", validators=[Optional(), Length(max=40)])
    website = StringField("Web sitesi", validators=[Optional(), Length(max=500)])
    status = SelectField(
        "Durum",
        choices=[(item.value, item.value) for item in OrganizationStatus],
        validators=[InputRequired()],
    )


class BrandingForm(FlaskForm):  # type: ignore[misc]
    company_display_name = StringField(
        "Görünen firma adı", validators=[Optional(), Length(max=160)]
    )
    primary_color = StringField(
        "Ana renk",
        validators=[Optional(), Regexp(HEX_COLOR, message="Renk #RRGGBB biçiminde olmalıdır.")],
    )
    secondary_color = StringField(
        "İkincil renk",
        validators=[Optional(), Regexp(HEX_COLOR, message="Renk #RRGGBB biçiminde olmalıdır.")],
    )
    surface_color = StringField(
        "Yüzey rengi",
        validators=[Optional(), Regexp(HEX_COLOR, message="Renk #RRGGBB biçiminde olmalıdır.")],
    )
    panel_title = StringField("Panel başlığı", validators=[Optional(), Length(max=120)])
    login_message = TextAreaField("Giriş mesajı", validators=[Optional(), Length(max=500)])
    white_label_enabled = BooleanField("White-label etkin")


class DomainForm(FlaskForm):  # type: ignore[misc]
    hostname = StringField("Hostname", validators=[InputRequired(), Length(max=253)])
    domain_type = SelectField(
        "Domain türü",
        choices=[(item.value, item.value) for item in DomainType],
        validators=[InputRequired()],
    )
    is_primary = BooleanField("Primary domain")


class OrganizationAdminForm(FlaskForm):  # type: ignore[misc]
    email = EmailField("E-posta", validators=[InputRequired(), Email(), Length(max=254)])
    first_name = StringField("Ad", validators=[Optional(), Length(max=100)])
    last_name = StringField("Soyad", validators=[Optional(), Length(max=100)])
    phone = StringField("Telefon", validators=[Optional(), Length(max=40)])
    temporary_password = PasswordField("Geçici parola", validators=[Optional()])
