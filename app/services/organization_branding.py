from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from email_validator import EmailNotValidError, validate_email
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from app.models import Organization, OrganizationBranding
from app.services import ServiceValidationError, SessionLike

DEFAULT_PRIMARY = "#0f3f3f"
DEFAULT_SECONDARY = "#d4d9d5"
DEFAULT_BACKGROUND = "#f4f4f4"
DEFAULT_SURFACE = "#ffffff"
DEFAULT_TEXT = "#0f3f3f"
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ASSET_KEY = re.compile(
    r"^(?P<organization>[0-9a-f-]{36})/(?P<name>[0-9a-f]{32})"
    r"(?P<extension>\.png|\.jpg|\.webp)$"
)
IMAGE_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}
MAX_IMAGE_PIXELS = 20_000_000


@dataclass(frozen=True, slots=True)
class EffectiveBranding:
    organization_id: uuid.UUID | None
    display_name: str
    short_name: str
    logo_asset_key: str | None
    primary_color: str
    secondary_color: str
    background_color: str
    surface_color: str
    text_color: str
    support_email: str | None
    support_phone: str | None
    website_url: str | None
    footer_text: str | None
    panel_title: str
    login_message: str
    is_tenant_branding: bool


@dataclass(frozen=True, slots=True)
class ValidatedLogo:
    content: bytes
    extension: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class BrandingUpdate:
    branding: OrganizationBranding
    previous_logo_asset_key: str | None


def normalize_color(value: str | None, *, fallback: str | None = None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return fallback
    if HEX_COLOR.fullmatch(candidate) is None:
        raise ServiceValidationError("Renk #RRGGBB biçiminde olmalıdır.")
    return candidate.lower()


def _effective_color(value: str | None, fallback: str) -> str:
    try:
        return normalize_color(value, fallback=fallback) or fallback
    except ServiceValidationError:
        return fallback


def _optional_text(value: str | None, *, maximum: int, label: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if len(candidate) > maximum:
        raise ServiceValidationError(f"{label} en fazla {maximum} karakter olabilir.")
    if any(ord(character) < 32 and character not in "\t\n" for character in candidate):
        raise ServiceValidationError(f"{label} geçersiz karakter içeriyor.")
    return candidate


def _email(value: str | None) -> str | None:
    candidate = _optional_text(value, maximum=254, label="Destek e-postası")
    if candidate is None:
        return None
    try:
        return validate_email(candidate, check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise ServiceValidationError("Geçerli bir destek e-postası girin.") from error


def _website(value: str | None) -> str | None:
    candidate = _optional_text(value, maximum=500, label="Web sitesi")
    if candidate is None:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ServiceValidationError("Web sitesi http veya https adresi olmalıdır.")
    if parsed.username or parsed.password:
        raise ServiceValidationError("Web sitesi kullanıcı bilgisi içeremez.")
    return candidate


def get_effective_branding(
    session: SessionLike,
    *,
    organization_id: uuid.UUID | None,
) -> EffectiveBranding:
    if organization_id is None:
        return EffectiveBranding(
            organization_id=None,
            display_name="Yapıbina",
            short_name="Yapıbina",
            logo_asset_key=None,
            primary_color=DEFAULT_PRIMARY,
            secondary_color=DEFAULT_SECONDARY,
            background_color=DEFAULT_BACKGROUND,
            surface_color=DEFAULT_SURFACE,
            text_color=DEFAULT_TEXT,
            support_email=None,
            support_phone=None,
            website_url=None,
            footer_text=None,
            panel_title="Yapıbina",
            login_message="Hesabınıza güvenli biçimde giriş yapın.",
            is_tenant_branding=False,
        )
    row = session.execute(
        select(Organization, OrganizationBranding)
        .outerjoin(
            OrganizationBranding,
            OrganizationBranding.organization_id == Organization.id,
        )
        .where(Organization.id == organization_id)
    ).one_or_none()
    if row is None:
        raise ServiceValidationError("Organization bulunamadı.")
    organization, branding = row
    display_name = (
        branding.company_display_name
        if branding is not None and branding.company_display_name
        else organization.name
    )
    short_name = (
        branding.short_name
        if branding is not None and branding.short_name
        else display_name
    )
    return EffectiveBranding(
        organization_id=organization.id,
        display_name=display_name,
        short_name=short_name,
        logo_asset_key=branding.logo_storage_key if branding is not None else None,
        primary_color=_effective_color(
            branding.primary_color if branding is not None else None,
            DEFAULT_PRIMARY,
        ),
        secondary_color=_effective_color(
            branding.secondary_color if branding is not None else None,
            DEFAULT_SECONDARY,
        ),
        background_color=_effective_color(
            branding.background_color if branding is not None else None,
            DEFAULT_BACKGROUND,
        ),
        surface_color=_effective_color(
            branding.surface_color if branding is not None else None,
            DEFAULT_SURFACE,
        ),
        text_color=_effective_color(
            branding.text_color if branding is not None else None,
            DEFAULT_TEXT,
        ),
        support_email=(
            branding.support_email
            if branding is not None and branding.support_email
            else organization.support_email
        ),
        support_phone=(
            branding.support_phone
            if branding is not None and branding.support_phone
            else organization.phone
        ),
        website_url=(
            branding.website_url
            if branding is not None and branding.website_url
            else organization.website
        ),
        footer_text=branding.footer_text if branding is not None else None,
        panel_title=(
            branding.panel_title
            if branding is not None and branding.panel_title
            else short_name
        ),
        login_message=(
            branding.login_message
            if branding is not None and branding.login_message
            else "Hesabınıza güvenli biçimde giriş yapın."
        ),
        is_tenant_branding=True,
    )


def update_organization_branding(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    display_name: str | None,
    short_name: str | None,
    primary_color: str | None,
    secondary_color: str | None,
    background_color: str | None,
    surface_color: str | None,
    support_email: str | None,
    support_phone: str | None,
    website_url: str | None,
    footer_text: str | None,
    logo_asset_key: str | None,
    panel_title: str | None = None,
    login_message: str | None = None,
) -> BrandingUpdate:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise ServiceValidationError("Organization bulunamadı.")
    branding = session.scalar(
        select(OrganizationBranding).where(
            OrganizationBranding.organization_id == organization_id
        )
    )
    if branding is None:
        branding = OrganizationBranding(organization_id=organization_id)
        session.add(branding)
    previous_logo = branding.logo_storage_key
    branding.company_display_name = _optional_text(
        display_name, maximum=160, label="Görünen marka adı"
    )
    branding.short_name = _optional_text(short_name, maximum=60, label="Kısa ad")
    branding.primary_color = normalize_color(primary_color)
    branding.secondary_color = normalize_color(secondary_color)
    branding.background_color = normalize_color(background_color)
    branding.surface_color = normalize_color(surface_color)
    branding.support_email = _email(support_email)
    branding.support_phone = _optional_text(
        support_phone, maximum=40, label="Destek telefonu"
    )
    branding.website_url = _website(website_url)
    branding.footer_text = _optional_text(
        footer_text, maximum=300, label="Footer metni"
    )
    branding.panel_title = _optional_text(
        panel_title, maximum=120, label="Panel başlığı"
    )
    branding.login_message = _optional_text(
        login_message, maximum=500, label="Giriş mesajı"
    )
    branding.logo_storage_key = logo_asset_key
    branding.white_label_enabled = True
    session.flush()
    return BrandingUpdate(branding=branding, previous_logo_asset_key=previous_logo)


def validate_logo(content: bytes, *, maximum_bytes: int) -> ValidatedLogo:
    if not content:
        raise ServiceValidationError("Logo dosyası boş olamaz.")
    if len(content) > maximum_bytes:
        raise ServiceValidationError("Logo dosyası izin verilen boyutu aşıyor.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ServiceValidationError("Logo görselinin çözünürlüğü çok büyük.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ServiceValidationError("Logo geçerli bir PNG, JPEG veya WebP değil.") from error
    if image_format not in IMAGE_FORMATS:
        raise ServiceValidationError("Yalnız PNG, JPEG veya WebP logo kabul edilir.")
    extension, mime_type = IMAGE_FORMATS[image_format]
    return ValidatedLogo(content=content, extension=extension, mime_type=mime_type)


def store_logo(
    storage_root: Path,
    *,
    organization_id: uuid.UUID,
    logo: ValidatedLogo,
) -> str:
    organization_directory = storage_root.resolve() / str(organization_id)
    try:
        organization_directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{logo.extension}"
        target = (organization_directory / filename).resolve()
        if target.parent != organization_directory:
            raise ServiceValidationError("Logo storage yolu güvenli değil.")
        target.write_bytes(logo.content)
    except OSError as error:
        raise ServiceValidationError("Logo güvenli storage alanına yazılamadı.") from error
    return f"{organization_id}/{filename}"


def resolve_logo_path(
    storage_root: Path,
    *,
    organization_id: uuid.UUID,
    asset_key: str,
) -> Path:
    match = ASSET_KEY.fullmatch(asset_key)
    if match is None or match.group("organization") != str(organization_id):
        raise ServiceValidationError("Logo asset kaydı geçersiz.")
    root = storage_root.resolve()
    path = (root / asset_key).resolve()
    if root not in path.parents:
        raise ServiceValidationError("Logo storage yolu güvenli değil.")
    return path


def delete_logo(
    storage_root: Path,
    *,
    organization_id: uuid.UUID,
    asset_key: str | None,
) -> None:
    if asset_key is None:
        return
    path = resolve_logo_path(
        storage_root,
        organization_id=organization_id,
        asset_key=asset_key,
    )
    path.unlink(missing_ok=True)
