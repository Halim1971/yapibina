from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, SelectField, StringField
from wtforms.fields import DateTimeLocalField
from wtforms.validators import Email, InputRequired, Length, Optional

from app.models import (
    ApartmentMembershipRole,
    BuildingMembershipRole,
    OrganizationMembershipRole,
)


class BuildingForm(FlaskForm):  # type: ignore[misc]
    name = StringField("Bina adı", validators=[InputRequired(), Length(max=160)])
    code = StringField("Bina kodu", validators=[InputRequired(), Length(max=50)])
    address_line = StringField("Adres", validators=[Optional(), Length(max=300)])
    district = StringField("İlçe", validators=[Optional(), Length(max=100)])
    city = StringField("Şehir", validators=[Optional(), Length(max=100)])
    postal_code = StringField("Posta kodu", validators=[Optional(), Length(max=20)])
    is_active = BooleanField("Aktif", default=True)


class ApartmentForm(FlaskForm):  # type: ignore[misc]
    number = StringField("Daire numarası", validators=[InputRequired(), Length(max=30)])
    floor = StringField("Kat", validators=[Optional(), Length(max=30)])
    block = StringField("Blok", validators=[Optional(), Length(max=30)])
    unit_code = StringField("Daire kodu", validators=[InputRequired(), Length(max=60)])
    is_active = BooleanField("Aktif", default=True)


class UserForm(FlaskForm):  # type: ignore[misc]
    email = EmailField("E-posta", validators=[InputRequired(), Email(), Length(max=254)])
    first_name = StringField("Ad", validators=[Optional(), Length(max=100)])
    last_name = StringField("Soyad", validators=[Optional(), Length(max=100)])
    phone = StringField("Telefon", validators=[Optional(), Length(max=40)])
    temporary_password = PasswordField("Geçici parola", validators=[Optional()])
    organization_role = SelectField(
        "Organization rolü",
        choices=[(item.value, item.value) for item in OrganizationMembershipRole],
        validators=[InputRequired()],
    )


class MembershipForm(FlaskForm):  # type: ignore[misc]
    role = SelectField("Rol", validators=[InputRequired()])
    resource_id = SelectField("Kaynak", validators=[Optional()])
    starts_at = DateTimeLocalField("Başlangıç", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    ends_at = DateTimeLocalField("Bitiş", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    is_active = BooleanField("Aktif", default=True)

    def set_organization_roles(self) -> None:
        self.role.choices = [(item.value, item.value) for item in OrganizationMembershipRole]

    def set_building_roles(self) -> None:
        self.role.choices = [(item.value, item.value) for item in BuildingMembershipRole]

    def set_apartment_roles(self) -> None:
        self.role.choices = [(item.value, item.value) for item in ApartmentMembershipRole]
