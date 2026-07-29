from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select
from werkzeug.test import TestResponse

from app.extensions import db
from app.imports.exceptions import CriticalFinancialChangeError
from app.imports.models import ImportRun
from app.imports.schemas import ImportResult
from app.models import (
    Building,
    DomainState,
    DomainType,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    User,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA = PROJECT_ROOT / "demo_data"
HOST = "import.example.com"
PASSWORD = "SecurePass123"


@pytest.fixture(autouse=True)
def _application_context(app: Flask, tmp_path: Path) -> None:
    app.instance_path = str(tmp_path / "instance")


def _user(email: str) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="İçe",
        last_name="Aktaran",
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _organization(slug: str, host: str) -> Organization:
    organization = Organization(
        name=slug.title(),
        slug=slug,
        status=OrganizationStatus.ACTIVE,
    )
    db.session.add(organization)
    db.session.flush()
    db.session.add(
        OrganizationDomain(
            organization_id=organization.id,
            hostname=host,
            domain_type=DomainType.CUSTOM_DOMAIN,
            state=DomainState.ACTIVE,
            is_active=True,
            is_primary=True,
        )
    )
    db.session.flush()
    return organization


def _seed_admin(
    *,
    role: OrganizationMembershipRole = OrganizationMembershipRole.ORGANIZATION_ADMIN,
) -> tuple[Organization, User]:
    organization = _organization("import", HOST)
    user = _user(f"{role.value}@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    db.session.commit()
    return organization, user


def _authenticate(client: FlaskClient, user: User, host: str = HOST) -> None:
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": PASSWORD},
        headers={"Host": host},
    )
    assert response.status_code == 302


def _package_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEMO_DATA.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DEMO_DATA).as_posix())
    return output.getvalue()


def _upload(
    client: FlaskClient,
    content: bytes,
    *,
    filename: str = "yapibina-demo.zip",
) -> TestResponse:
    return client.post(
        "/organization/imports/new",
        data={"package": (io.BytesIO(content), filename, "application/zip")},
        headers={"Host": HOST},
        content_type="multipart/form-data",
    )


def _confirm_fields(response_data: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name in ("staging_token", "fingerprint"):
        match = re.search(
            rb'name="' + name.encode() + rb'"[^>]*value="([^"]+)"',
            response_data,
        )
        assert match is not None
        fields[name] = match.group(1).decode()
    return fields


def test_access_is_limited_to_organization_admin(client: FlaskClient) -> None:
    _, member = _seed_admin(role=OrganizationMembershipRole.ORGANIZATION_MEMBER)
    response = client.get("/organization/imports", headers={"Host": HOST})
    assert response.status_code == 302

    _authenticate(client, member)
    assert client.get("/organization/imports", headers={"Host": HOST}).status_code == 403


def test_invalid_extension_content_and_size_are_rejected(
    app: Flask,
    client: FlaskClient,
) -> None:
    _, admin = _seed_admin()
    _authenticate(client, admin)
    wrong_extension = _upload(client, b"PK-not-really-zip", filename="package.xlsx")
    assert wrong_extension.status_code == 200
    assert "Yalnız ZIP".encode() in wrong_extension.data

    wrong_content = _upload(client, b"not-a-zip")
    assert wrong_content.status_code == 200
    assert "geçerli bir ZIP".encode() in wrong_content.data

    app.config["IMPORT_PACKAGE_MAX_BYTES"] = 10
    too_large = _upload(client, _package_zip())
    assert too_large.status_code == 200
    assert "boyutu aşıyor".encode() in too_large.data

    app.config["IMPORT_PACKAGE_MAX_BYTES"] = 10_485_760
    traversal_buffer = io.BytesIO()
    with zipfile.ZipFile(traversal_buffer, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")
    traversal = _upload(client, traversal_buffer.getvalue())
    assert traversal.status_code == 200
    assert "güvenli olmayan".encode() in traversal.data


def test_dry_run_confirm_real_import_history_and_cleanup(
    app: Flask,
    client: FlaskClient,
) -> None:
    organization, admin = _seed_admin()
    _authenticate(client, admin)

    preview = _upload(client, _package_zip())
    assert preview.status_code == 200
    assert "Paket doğrulandı".encode() in preview.data
    assert b">305<" in preview.data
    fields = _confirm_fields(preview.data)
    staging_directory = (
        Path(app.instance_path)
        / "import_staging"
        / str(organization.id)
        / fields["staging_token"]
    )
    assert staging_directory.is_dir()

    missing_preview = client.post(
        "/organization/imports/confirm",
        data={"staging_token": "0" * 32, "fingerprint": "0" * 64},
        headers={"Host": HOST},
    )
    assert missing_preview.status_code == 400

    confirmed = client.post(
        "/organization/imports/confirm",
        data=fields,
        headers={"Host": HOST},
    )
    assert confirmed.status_code == 302
    assert "/organization/imports/" in confirmed.location
    assert not staging_directory.exists()
    assert db.session.scalar(
        select(func.count()).select_from(Building).where(
            Building.organization_id == organization.id
        )
    ) == 5
    run = db.session.scalar(
        select(ImportRun).where(ImportRun.organization_id == organization.id)
    )
    assert run is not None
    assert run.created_by_user_id == admin.id

    detail = client.get(confirmed.location, headers={"Host": HOST})
    assert detail.status_code == 200
    assert "Tamamlandı".encode() in detail.data
    history = client.get("/organization/imports", headers={"Host": HOST})
    assert history.status_code == 200
    assert b"305 yeni" not in history.data
    assert "Tamamlandı".encode() in history.data

    duplicate_submit = client.post(
        "/organization/imports/confirm",
        data=fields,
        headers={"Host": HOST},
    )
    assert duplicate_submit.status_code == 400


def test_import_detail_is_tenant_scoped(client: FlaskClient) -> None:
    organization, admin = _seed_admin()
    other = _organization("other-import", "other-import.example.com")
    db.session.add(
        ImportRun(
            organization_id=other.id,
            source_system="standard_excel",
            dataset_name="Yabancı",
            dataset_version="1",
            schema_version="1",
            manifest_sha256="0" * 64,
            package_fingerprint="1" * 64,
        )
    )
    db.session.commit()
    foreign_run = db.session.scalar(
        select(ImportRun).where(ImportRun.organization_id == other.id)
    )
    assert foreign_run is not None
    _authenticate(client, admin)
    response = client.get(
        f"/organization/imports/{foreign_run.id}",
        headers={"Host": HOST},
    )
    assert response.status_code == 404
    assert organization.id != other.id


def test_duplicate_and_financial_conflict_preview_are_user_friendly(
    app: Flask,
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization, admin = _seed_admin()
    _authenticate(client, admin)

    def already_imported(*args: object, **kwargs: object) -> ImportResult:
        del args, kwargs
        return ImportResult(
            run_id="existing",
            status="already_imported",
            fingerprint="a" * 64,
            inserted=0,
            updated=0,
            skipped=665,
            deferred=155,
        )

    monkeypatch.setattr(
        "app.blueprints.organization.import_routes.import_standard_package",
        already_imported,
    )
    duplicate = _upload(client, _package_zip())
    assert duplicate.status_code == 200
    assert "daha önce içe aktarılmış".encode() in duplicate.data

    def conflict(*args: object, **kwargs: object) -> ImportResult:
        del args, kwargs
        raise CriticalFinancialChangeError("critical source conflict")

    monkeypatch.setattr(
        "app.blueprints.organization.import_routes.import_standard_package",
        conflict,
    )
    conflicted = _upload(client, _package_zip())
    assert conflicted.status_code == 200
    assert "Finansal kayıt çakışması".encode() in conflicted.data
    staging_root = (
        Path(app.instance_path) / "import_staging" / str(organization.id)
    )
    assert not staging_root.exists()


def test_import_post_requires_csrf(
    app: Flask,
    client: FlaskClient,
) -> None:
    _, admin = _seed_admin()
    _authenticate(client, admin)
    app.config["WTF_CSRF_ENABLED"] = True
    response = _upload(client, _package_zip())
    assert response.status_code == 400
    assert "Güvenlik doğrulaması başarısız".encode() in response.data
