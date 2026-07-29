from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    DecimalField,
    EmailField,
    HiddenField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.fields import DateField, DateTimeLocalField
from wtforms.validators import (
    Email,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)

from app.models import (
    ApartmentMembershipRole,
    BuildingMembershipRole,
    OrganizationMembershipRole,
)

MONTH_CHOICES = [
    (1, "Ocak"),
    (2, "Şubat"),
    (3, "Mart"),
    (4, "Nisan"),
    (5, "Mayıs"),
    (6, "Haziran"),
    (7, "Temmuz"),
    (8, "Ağustos"),
    (9, "Eylül"),
    (10, "Ekim"),
    (11, "Kasım"),
    (12, "Aralık"),
]


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


class DuesPeriodFilterForm(FlaskForm):  # type: ignore[misc]
    class Meta:
        csrf = False

    building_id = SelectField("Bina", validators=[InputRequired()])
    year = SelectField("Yıl", coerce=int, validators=[InputRequired()])
    month = SelectField(
        "Ay",
        coerce=int,
        choices=MONTH_CHOICES,
        validators=[InputRequired()],
    )

    def set_choices(self, buildings: list[tuple[str, str]], current_year: int) -> None:
        self.building_id.choices = buildings
        self.year.choices = [
            (year, str(year)) for year in range(current_year - 5, current_year + 6)
        ]


class ChargeBatchCreateForm(FlaskForm):  # type: ignore[misc]
    building_id = SelectField("Bina", validators=[InputRequired()])
    period_year = SelectField("Yıl", coerce=int, validators=[InputRequired()])
    period_month = SelectField(
        "Ay",
        coerce=int,
        choices=MONTH_CHOICES,
        validators=[InputRequired()],
    )
    title = StringField("Aidat başlığı", validators=[InputRequired(), Length(max=160)])
    default_amount = DecimalField(
        "Aidat tutarı",
        places=2,
        rounding=None,
        validators=[InputRequired(), NumberRange(min=0.01)],
    )
    due_date = DateField("Son ödeme tarihi", validators=[InputRequired()])
    description = TextAreaField(
        "Açıklama",
        validators=[Optional(), Length(max=500)],
    )

    def set_choices(self, buildings: list[tuple[str, str]], current_year: int) -> None:
        self.building_id.choices = buildings
        self.period_year.choices = [
            (year, str(year)) for year in range(current_year - 5, current_year + 6)
        ]


class PaymentCreateForm(FlaskForm):  # type: ignore[misc]
    amount = DecimalField(
        "Tutar",
        places=2,
        rounding=None,
        validators=[InputRequired(), NumberRange(min=0.01)],
    )
    payment_date = DateField(
        "Ödeme tarihi",
        validators=[InputRequired()],
        default=date.today,
    )
    payment_method = SelectField(
        "Ödeme yöntemi",
        choices=[
            ("cash", "Nakit"),
            ("bank_transfer", "Havale/EFT"),
            ("card", "Kart"),
            ("other", "Diğer"),
        ],
        validators=[InputRequired()],
    )
    reference = StringField(
        "Referans",
        validators=[Optional(), Length(max=120)],
    )
    description = TextAreaField(
        "Açıklama",
        validators=[Optional(), Length(max=500)],
    )
    auto_allocate = BooleanField(
        "Ödemeyi en eski açık borçtan başlayarak işle",
        default=True,
    )


class ImportPackageForm(FlaskForm):  # type: ignore[misc]
    package = FileField("Canonical veri paketi (.zip)", validators=[InputRequired()])


class ImportConfirmForm(FlaskForm):  # type: ignore[misc]
    staging_token = HiddenField(validators=[InputRequired()])
    fingerprint = HiddenField(validators=[InputRequired(), Length(min=64, max=64)])
