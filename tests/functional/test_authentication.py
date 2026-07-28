from __future__ import annotations

import re
from datetime import timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from app.extensions import db
from app.models import (
    DomainState,
    DomainType,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    User,
    UserStatus,
)
from app.models.base import utc_now

PASSWORD = "SecurePassword123"
INVALID_MESSAGE = "E-posta adresi veya parola hatalı."


def seed_tenant_user(
    *,
    hostname: str = "tenant.example.com",
    email: str = "member@example.com",
    user_status: UserStatus = UserStatus.ACTIVE,
    organization_status: OrganizationStatus = OrganizationStatus.ACTIVE,
    membership_active: bool = True,
    membership_ended: bool = False,
) -> tuple[Organization, User, OrganizationMembership]:
    organization = Organization(
        name="Tenant",
        slug=hostname.split(".")[0],
        status=organization_status,
    )
    user = User(
        email=email,
        password_hash="pending",
        first_name="Tenant",
        last_name="User",
        status=user_status,
    )
    user.set_password(PASSWORD)
    db.session.add_all([organization, user])
    db.session.flush()
    domain = OrganizationDomain(
        organization_id=organization.id,
        hostname=hostname,
        domain_type=DomainType.CUSTOM_DOMAIN,
        state=DomainState.ACTIVE,
        is_active=True,
        is_primary=True,
    )
    now = utc_now()
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        is_active=membership_active,
        starts_at=now - timedelta(days=2),
        ends_at=now - timedelta(days=1) if membership_ended else None,
    )
    db.session.add_all([domain, membership])
    db.session.commit()
    return organization, user, membership


def login(
    client: FlaskClient,
    *,
    hostname: str = "tenant.example.com",
    email: str = "member@example.com",
    password: str = PASSWORD,
    query_string: str = "",
) -> TestResponse:
    return client.post(
        f"/auth/login{query_string}",
        data={"email": email, "password": password},
        headers={"Host": hostname},
    )


def test_login_succeeds_for_matching_tenant_membership(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    seed_tenant_user()

    response = login(client)

    assert response.status_code == 302
    assert response.location == "/organization/"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("member@example.com", "WrongPassword123"),
        ("missing@example.com", PASSWORD),
    ],
)
def test_invalid_credentials_use_same_message(
    app: Flask,
    client: FlaskClient,
    email: str,
    password: str,
) -> None:
    del app
    seed_tenant_user()

    response = login(client, email=email, password=password)

    assert response.status_code == 200
    assert INVALID_MESSAGE.encode() in response.data


@pytest.mark.parametrize("status", [UserStatus.INACTIVE, UserStatus.LOCKED])
def test_inactive_or_locked_user_cannot_login(
    app: Flask,
    client: FlaskClient,
    status: UserStatus,
) -> None:
    del app
    seed_tenant_user(user_status=status)

    response = login(client)

    assert response.status_code == 200
    assert INVALID_MESSAGE.encode() in response.data


def test_user_from_another_organization_cannot_login(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    seed_tenant_user(hostname="first.example.com", email="first@example.com")
    seed_tenant_user(hostname="second.example.com", email="second@example.com")

    response = login(
        client,
        hostname="first.example.com",
        email="second@example.com",
    )

    assert response.status_code == 200
    assert INVALID_MESSAGE.encode() in response.data


@pytest.mark.parametrize(
    ("membership_active", "membership_ended"),
    [(False, False), (True, True)],
)
def test_inactive_or_expired_membership_cannot_login(
    app: Flask,
    client: FlaskClient,
    membership_active: bool,
    membership_ended: bool,
) -> None:
    del app
    seed_tenant_user(
        membership_active=membership_active,
        membership_ended=membership_ended,
    )

    response = login(client)

    assert response.status_code == 200
    assert INVALID_MESSAGE.encode() in response.data


def test_suspended_organization_is_rejected_before_login(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    seed_tenant_user(organization_status=OrganizationStatus.SUSPENDED)

    response = login(client)

    assert response.status_code == 421


def test_tenant_user_cannot_login_on_platform_hostname(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    seed_tenant_user()

    response = login(client, hostname="platform.yapibina.com")

    assert response.status_code == 200
    assert INVALID_MESSAGE.encode() in response.data


def test_platform_admin_can_login_only_on_platform(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    organization, user, _ = seed_tenant_user(email="platform@example.com")
    user.is_platform_super_admin = True
    db.session.commit()

    platform_response = login(
        client,
        hostname="platform.yapibina.com",
        email=user.email,
    )
    assert platform_response.status_code == 302
    assert platform_response.location == "/platform/"

    client.post("/auth/logout", headers={"Host": "platform.yapibina.com"})
    tenant_response = login(
        client,
        hostname="tenant.example.com",
        email=user.email,
    )
    assert tenant_response.status_code == 200
    assert INVALID_MESSAGE.encode() in tenant_response.data
    assert organization.status is OrganizationStatus.ACTIVE


def test_successful_login_updates_last_login_at(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    _, user, _ = seed_tenant_user()
    assert user.last_login_at is None

    login(client)
    db.session.refresh(user)

    assert user.last_login_at is not None


def test_login_get_renders_form(app: Flask, client: FlaskClient) -> None:
    del app
    seed_tenant_user()

    response = client.get("/auth/login", headers={"Host": "tenant.example.com"})

    assert response.status_code == 200
    assert b'name="email"' in response.data
    assert b'name="password"' in response.data
    assert b'name="remember_me"' in response.data


def test_logout_is_post_only_and_revokes_access(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    seed_tenant_user()
    login(client)

    assert client.get(
        "/auth/logout",
        headers={"Host": "tenant.example.com"},
    ).status_code == 405
    response = client.post(
        "/auth/logout",
        headers={"Host": "tenant.example.com"},
    )
    assert response.status_code == 302
    protected = client.get(
        "/organization/",
        headers={"Host": "tenant.example.com"},
    )
    assert protected.status_code == 302
    assert "/auth/login" in protected.location


def test_inactive_user_loses_existing_session(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    _, user, _ = seed_tenant_user()
    login(client)
    user.status = UserStatus.INACTIVE
    db.session.commit()

    response = client.get(
        "/organization/",
        headers={"Host": "tenant.example.com"},
    )

    assert response.status_code == 302
    assert "/auth/login" in response.location


def test_inactive_membership_loses_existing_session(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    _, _, membership = seed_tenant_user()
    login(client)
    membership.is_active = False
    db.session.commit()

    response = client.get(
        "/organization/",
        headers={"Host": "tenant.example.com"},
    )

    assert response.status_code == 403


def test_expired_membership_loses_existing_session(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    _, _, membership = seed_tenant_user()
    login(client)
    membership.ends_at = utc_now() - timedelta(seconds=1)
    db.session.commit()

    response = client.get(
        "/organization/",
        headers={"Host": "tenant.example.com"},
    )

    assert response.status_code == 403


def test_suspended_organization_cuts_existing_session_access(
    app: Flask,
    client: FlaskClient,
) -> None:
    del app
    organization, _, _ = seed_tenant_user()
    login(client)
    organization.status = OrganizationStatus.SUSPENDED
    db.session.commit()

    response = client.get(
        "/organization/",
        headers={"Host": "tenant.example.com"},
    )

    assert response.status_code == 421


@pytest.mark.parametrize(
    ("next_url", "expected"),
    [
        ("/organization/safe", "/organization/safe"),
        ("https://evil.example/path", "/organization/"),
        ("//evil.example/path", "/organization/"),
    ],
)
def test_next_redirect_validation(
    app: Flask,
    client: FlaskClient,
    next_url: str,
    expected: str,
) -> None:
    del app
    seed_tenant_user()

    response = login(client, query_string=f"?next={next_url}")

    assert response.status_code == 302
    assert response.location == expected


def _csrf_token(response_data: bytes) -> str:
    match = re.search(rb'name="csrf_token" type="hidden" value="([^"]+)"', response_data)
    assert match is not None
    return match.group(1).decode()


def test_login_post_requires_csrf_when_enabled(
    app: Flask,
    client: FlaskClient,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    seed_tenant_user()

    rejected = login(client)
    assert rejected.status_code == 400
    assert b"csrf" not in rejected.data.lower()

    form = client.get("/auth/login", headers={"Host": "tenant.example.com"})
    token = _csrf_token(form.data)
    accepted = client.post(
        "/auth/login",
        data={
            "email": "member@example.com",
            "password": PASSWORD,
            "csrf_token": token,
        },
        headers={"Host": "tenant.example.com"},
    )
    assert accepted.status_code == 302


def test_csrf_json_error_is_safe(app: Flask, client: FlaskClient) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    seed_tenant_user()

    response = client.post(
        "/auth/login",
        data={"email": "member@example.com", "password": PASSWORD},
        headers={
            "Host": "tenant.example.com",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]["code"] == 400
    assert "token" not in payload["error"]["message"].lower()


def test_logout_post_is_csrf_protected(app: Flask, client: FlaskClient) -> None:
    seed_tenant_user()
    login(client)
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/auth/logout",
        headers={"Host": "tenant.example.com"},
    )

    assert response.status_code == 400


def test_login_rate_limit_returns_generic_429(
    app: Flask,
    client: FlaskClient,
) -> None:
    app.config["RATELIMIT_ENABLED"] = True
    app.config["LOGIN_RATE_LIMITS"] = "2 per minute"
    seed_tenant_user()

    login(client, password="WrongPassword123")
    login(client, password="WrongPassword123")
    response = login(client, password="WrongPassword123")

    assert response.status_code == 429
    assert b"fazla" in response.data
    assert b"member@example.com" not in response.data
