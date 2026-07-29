from __future__ import annotations

import io
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from PIL import Image
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Apartment,
    ApartmentMembership,
    ApartmentMembershipRole,
    Building,
    BuildingMembership,
    BuildingMembershipRole,
    DomainState,
    DomainType,
    Organization,
    OrganizationBranding,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    User,
)
from app.services import ServiceValidationError
from app.services.organization_branding import (
    DEFAULT_BACKGROUND,
    DEFAULT_PRIMARY,
    get_effective_branding,
    normalize_color,
    update_organization_branding,
    validate_logo,
)

HOST = "brand.example.com"
PASSWORD = "SecurePass123"


@pytest.fixture(autouse=True)
def _isolated_branding_storage(app: Flask, tmp_path: Path) -> None:
    app.instance_path = str(tmp_path / "instance")


def _user(email: str) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="Marka",
        last_name="Kullanıcısı",
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _organization(slug: str, hostname: str) -> Organization:
    organization = Organization(
        name=f"{slug.title()} Yönetimi",
        slug=slug,
        status=OrganizationStatus.ACTIVE,
        support_email=f"destek@{slug}.example.com",
    )
    db.session.add(organization)
    db.session.flush()
    db.session.add(
        OrganizationDomain(
            organization_id=organization.id,
            hostname=hostname,
            domain_type=DomainType.CUSTOM_DOMAIN,
            state=DomainState.ACTIVE,
            is_active=True,
            is_primary=True,
        )
    )
    db.session.flush()
    return organization


def _admin_scope() -> tuple[Organization, User]:
    organization = _organization("brand", HOST)
    admin = _user("brand-admin@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=admin.id,
            role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    )
    db.session.commit()
    return organization, admin


def _login(client: FlaskClient, user: User, host: str = HOST) -> None:
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": PASSWORD},
        headers={"Host": host},
    )
    assert response.status_code == 302


def _image_bytes(image_format: str = "PNG", *, size: tuple[int, int] = (20, 20)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, color=(15, 63, 63)).save(stream, format=image_format)
    return stream.getvalue()


def _branding_data(**overrides: str) -> dict[str, str]:
    data = {
        "display_name": "Örnek Yönetim",
        "short_name": "Örnek",
        "primary_color": "#AABBCC",
        "secondary_color": "#d4d9d5",
        "background_color": "#f4f4f4",
        "surface_color": "#ffffff",
        "support_email": "destek@example.com",
        "support_phone": "0212 000 00 00",
        "website_url": "https://example.com",
        "footer_text": "Örnek yönetim bilgilendirme paneli",
        "panel_title": "Örnek Panel",
        "login_message": "Örnek yönetim hesabınıza giriş yapın.",
    }
    data.update(overrides)
    return data


def test_effective_branding_fallback_normalization_and_unique_constraint() -> None:
    organization, _ = _admin_scope()
    effective = get_effective_branding(
        db.session,
        organization_id=organization.id,
    )
    assert effective.display_name == organization.name
    assert effective.primary_color == DEFAULT_PRIMARY
    assert effective.background_color == DEFAULT_BACKGROUND
    assert effective.support_email == organization.support_email
    assert normalize_color("#AABBCC") == "#aabbcc"

    update = update_organization_branding(
        db.session,
        organization_id=organization.id,
        display_name=" ",
        short_name=None,
        primary_color="#AABBCC",
        secondary_color=None,
        background_color=None,
        surface_color=None,
        support_email=None,
        support_phone=None,
        website_url="https://example.com",
        footer_text=None,
        logo_asset_key=None,
    )
    db.session.commit()
    assert update.branding.primary_color == "#aabbcc"
    assert (
        get_effective_branding(
            db.session,
            organization_id=organization.id,
        ).display_name
        == organization.name
    )
    db.session.add(OrganizationBranding(organization_id=organization.id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    with pytest.raises(ServiceValidationError):
        normalize_color("red")
    with pytest.raises(ServiceValidationError):
        update_organization_branding(
            db.session,
            organization_id=organization.id,
            display_name=None,
            short_name=None,
            primary_color=None,
            secondary_color=None,
            background_color=None,
            surface_color=None,
            support_email=None,
            support_phone=None,
            website_url="javascript:alert(1)",
            footer_text=None,
            logo_asset_key=None,
            panel_title=None,
            login_message=None,
        )


@pytest.mark.parametrize(
    ("image_format", "extension"),
    [("PNG", ".png"), ("JPEG", ".jpg"), ("WEBP", ".webp")],
)
def test_supported_logo_formats_are_detected_from_content(
    image_format: str,
    extension: str,
) -> None:
    logo = validate_logo(_image_bytes(image_format), maximum_bytes=2_097_152)
    assert logo.extension == extension


def test_branding_route_authorization_and_tenant_isolation(
    client: FlaskClient,
) -> None:
    organization, admin = _admin_scope()
    building = Building(organization_id=organization.id, name="Marka Binası", code="M")
    db.session.add(building)
    db.session.flush()
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="1",
        unit_code="M-1",
    )
    db.session.add(apartment)
    member = _user("brand-member@example.com")
    manager = _user("brand-manager@example.com")
    resident = _user("brand-resident@example.com")
    db.session.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=member.id,
                role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=manager.id,
                role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=resident.id,
                role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            ),
            BuildingMembership(
                organization_id=organization.id,
                building_id=building.id,
                user_id=manager.id,
                role=BuildingMembershipRole.BUILDING_MANAGER,
            ),
            ApartmentMembership(
                organization_id=organization.id,
                apartment_id=apartment.id,
                user_id=resident.id,
                role=ApartmentMembershipRole.RESIDENT,
            ),
        ]
    )
    other = _organization("other-brand", "other-brand.example.com")
    db.session.add(
        OrganizationBranding(
            organization_id=other.id,
            company_display_name="Gizli Marka",
            primary_color="#123456",
        )
    )
    db.session.commit()

    assert (
        client.get("/organization/settings/branding", headers={"Host": HOST}).status_code
        == 302
    )
    _login(client, admin)
    response = client.post(
        "/organization/settings/branding",
        data={**_branding_data(), "organization_id": str(other.id)},
        headers={"Host": HOST},
        follow_redirects=True,
    )
    assert response.status_code == 200
    own = db.session.scalar(
        select(OrganizationBranding).where(
            OrganizationBranding.organization_id == organization.id
        )
    )
    hidden = db.session.scalar(
        select(OrganizationBranding).where(
            OrganizationBranding.organization_id == other.id
        )
    )
    assert own is not None and own.company_display_name == "Örnek Yönetim"
    assert hidden is not None and hidden.company_display_name == "Gizli Marka"
    assert b"Gizli Marka" not in response.data

    for denied in (member, manager, resident):
        client.post("/auth/logout", headers={"Host": HOST})
        _login(client, denied)
        assert (
            client.get(
                "/organization/settings/branding", headers={"Host": HOST}
            ).status_code
            == 403
        )


def test_logo_validation_storage_replacement_and_tenant_scope(
    app: Flask,
    client: FlaskClient,
) -> None:
    organization, admin = _admin_scope()
    other = _organization("logo-other", "logo-other.example.com")
    db.session.commit()
    _login(client, admin)
    first = _image_bytes("PNG")
    response = client.post(
        "/organization/settings/branding",
        data={
            **_branding_data(),
            "logo": (io.BytesIO(first), "../../logo.svg", "image/svg+xml"),
        },
        content_type="multipart/form-data",
        headers={"Host": HOST},
    )
    assert response.status_code == 302
    branding = db.session.scalar(
        select(OrganizationBranding).where(
            OrganizationBranding.organization_id == organization.id
        )
    )
    assert branding is not None and branding.logo_storage_key is not None
    first_key = branding.logo_storage_key
    first_path = Path(app.instance_path) / "branding_assets" / first_key
    assert first_path.read_bytes() == first
    assert ".." not in first_key
    assert client.get("/organization/branding/logo", headers={"Host": HOST}).data == first
    assert (
        client.get(
            "/organization/branding/logo",
            headers={"Host": "logo-other.example.com"},
        ).status_code
        == 404
    )

    second = _image_bytes("WEBP")
    response = client.post(
        "/organization/settings/branding",
        data={
            **_branding_data(),
            "logo": (io.BytesIO(second), "same-name.png", "image/png"),
        },
        content_type="multipart/form-data",
        headers={"Host": HOST},
    )
    assert response.status_code == 302
    db.session.refresh(branding)
    assert branding.logo_storage_key != first_key
    assert not first_path.exists()
    assert (
        Path(app.instance_path) / "branding_assets" / branding.logo_storage_key
    ).is_file()
    assert other.id != organization.id


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("fake.png", b"not-an-image", "geçerli bir PNG"),
        ("vector.svg", b"<svg></svg>", "geçerli bir PNG"),
    ],
)
def test_invalid_logo_keeps_existing_asset(
    app: Flask,
    client: FlaskClient,
    filename: str,
    content: bytes,
    message: str,
) -> None:
    organization, admin = _admin_scope()
    existing = OrganizationBranding(
        organization_id=organization.id,
        logo_storage_key=f"{organization.id}/{'a' * 32}.png",
    )
    db.session.add(existing)
    path = (
        Path(app.instance_path)
        / "branding_assets"
        / str(organization.id)
        / f"{'a' * 32}.png"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(_image_bytes())
    db.session.commit()
    _login(client, admin)
    response = client.post(
        "/organization/settings/branding",
        data={
            **_branding_data(),
            "logo": (io.BytesIO(content), filename, "image/png"),
        },
        content_type="multipart/form-data",
        headers={"Host": HOST},
    )
    assert response.status_code == 200
    assert message.encode() in response.data
    db.session.refresh(existing)
    assert existing.logo_storage_key is not None
    assert existing.logo_storage_key.endswith(f"{'a' * 32}.png")
    assert path.is_file()


def test_oversized_logo_and_unsafe_text_are_rejected(
    app: Flask,
    client: FlaskClient,
) -> None:
    _, admin = _admin_scope()
    app.config["BRANDING_LOGO_MAX_BYTES"] = 10
    _login(client, admin)
    response = client.post(
        "/organization/settings/branding",
        data={
            **_branding_data(website_url="data:text/html,unsafe"),
            "logo": (io.BytesIO(_image_bytes()), "large.png", "image/png"),
        },
        content_type="multipart/form-data",
        headers={"Host": HOST},
    )
    assert response.status_code == 200
    assert b"http veya https" in response.data or b"izin verilen boyutu" in response.data
    escaped = client.post(
        "/organization/settings/branding",
        data=_branding_data(
            display_name="<script>alert(1)</script>",
            website_url="https://example.com",
        ),
        headers={"Host": HOST},
        follow_redirects=True,
    )
    assert b"&lt;script&gt;" in escaped.data
    assert b"<script>alert(1)</script>" not in escaped.data


def test_tenant_login_rendering_platform_fallback_and_query_budget(
    client: FlaskClient,
) -> None:
    organization, admin = _admin_scope()
    db.session.add(
        OrganizationBranding(
            organization_id=organization.id,
            company_display_name="Tam Beyaz Marka",
            short_name="TBM",
            primary_color="#112233",
            background_color="#eeeeee",
            surface_color="#ffffff",
            footer_text="Yalnız müşteri markası",
            white_label_enabled=True,
        )
    )
    db.session.commit()
    statements = 0

    def count_query(*_: object) -> None:
        nonlocal statements
        statements += 1

    engine = db.session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        tenant_login = client.get("/auth/login", headers={"Host": HOST})
    finally:
        event.remove(engine, "before_cursor_execute", count_query)
    assert tenant_login.status_code == 200
    assert b"Tam Beyaz Marka" in tenant_login.data
    assert b"Yap\xc4\xb1bina" not in tenant_login.data
    assert b"--brand-primary: #112233" in tenant_login.data
    assert statements <= 2

    _login(client, admin)
    organization_page = client.get(
        "/organization/dashboard",
        headers={"Host": HOST},
    )
    assert organization_page.status_code == 200
    assert b">TBM</span>" in organization_page.data
    assert b"Yap\xc4\xb1bina" not in organization_page.data
    client.post("/auth/logout", headers={"Host": HOST})

    platform_login = client.get(
        "/auth/login",
        headers={"Host": "platform.yapibina.com"},
    )
    assert platform_login.status_code == 200
    assert b"Yap\xc4\xb1bina" in platform_login.data
    assert b"Tam Beyaz Marka" not in platform_login.data
