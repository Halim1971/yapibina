from __future__ import annotations

import uuid
from datetime import timedelta

from flask import Flask, Response, jsonify
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from app.auth.decorators import (
    building_access_required,
    organization_admin_required,
    platform_admin_required,
    resident_apartment_access_required,
)
from app.auth.policies import can_access_platform
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
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    User,
)
from app.models.base import utc_now

PASSWORD = "Authorization123"


def _protected_response(**_: object) -> Response:
    return jsonify(ok=True)


def register_test_routes(app: Flask) -> None:
    app.add_url_rule(
        "/test/platform-admin",
        endpoint="test_platform_admin",
        view_func=platform_admin_required(_protected_response),
    )
    app.add_url_rule(
        "/test/organization-admin",
        endpoint="test_organization_admin",
        view_func=organization_admin_required(_protected_response),
    )
    app.add_url_rule(
        "/test/buildings/<uuid:building_id>",
        endpoint="test_building_access",
        view_func=building_access_required(_protected_response),
    )
    app.add_url_rule(
        "/test/apartments/<uuid:apartment_id>",
        endpoint="test_apartment_access",
        view_func=resident_apartment_access_required(_protected_response),
    )


def _user(email: str) -> User:
    account = User(
        email=email,
        password_hash="pending",
        first_name="Auth",
        last_name="User",
    )
    account.set_password(PASSWORD)
    db.session.add(account)
    return account


def seed_authorization_data() -> dict[str, object]:
    now = utc_now()
    first = Organization(
        name="First",
        slug="first-auth",
        status=OrganizationStatus.ACTIVE,
    )
    second = Organization(
        name="Second",
        slug="second-auth",
        status=OrganizationStatus.ACTIVE,
    )
    db.session.add_all([first, second])
    db.session.flush()
    db.session.add(
        OrganizationDomain(
            organization_id=first.id,
            hostname="auth.example.com",
            domain_type=DomainType.CUSTOM_DOMAIN,
            state=DomainState.ACTIVE,
            is_active=True,
            is_primary=True,
        )
    )
    first_building = Building(
        organization_id=first.id,
        name="First",
        code="FIRST",
    )
    other_building = Building(
        organization_id=first.id,
        name="Other",
        code="OTHER",
    )
    cross_tenant_building = Building(
        organization_id=second.id,
        name="Cross",
        code="CROSS",
    )
    db.session.add_all([first_building, other_building, cross_tenant_building])
    db.session.flush()
    own_apartment = Apartment(
        organization_id=first.id,
        building_id=first_building.id,
        number="1",
        unit_code="1",
    )
    other_apartment = Apartment(
        organization_id=first.id,
        building_id=first_building.id,
        number="2",
        unit_code="2",
    )
    cross_apartment = Apartment(
        organization_id=second.id,
        building_id=cross_tenant_building.id,
        number="1",
        unit_code="1",
    )
    db.session.add_all([own_apartment, other_apartment, cross_apartment])
    db.session.flush()

    admin = _user("admin@example.com")
    manager = _user("manager@example.com")
    resident = _user("resident@example.com")
    db.session.flush()
    for account, role in (
        (admin, OrganizationMembershipRole.ORGANIZATION_ADMIN),
        (manager, OrganizationMembershipRole.ORGANIZATION_MEMBER),
        (resident, OrganizationMembershipRole.ORGANIZATION_MEMBER),
    ):
        db.session.add(
            OrganizationMembership(
                organization_id=first.id,
                user_id=account.id,
                role=role,
                starts_at=now - timedelta(days=1),
            )
        )
    db.session.add(
        BuildingMembership(
            organization_id=first.id,
            building_id=first_building.id,
            user_id=manager.id,
            role=BuildingMembershipRole.BUILDING_MANAGER,
            starts_at=now - timedelta(days=1),
        )
    )
    apartment_membership = ApartmentMembership(
        organization_id=first.id,
        apartment_id=own_apartment.id,
        user_id=resident.id,
        role=ApartmentMembershipRole.RESIDENT,
        starts_at=now - timedelta(days=1),
    )
    db.session.add(apartment_membership)
    db.session.commit()
    return {
        "admin": admin,
        "manager": manager,
        "resident": resident,
        "first_building": first_building,
        "other_building": other_building,
        "cross_building": cross_tenant_building,
        "own_apartment": own_apartment,
        "other_apartment": other_apartment,
        "cross_apartment": cross_apartment,
        "apartment_membership": apartment_membership,
    }


def login(client: FlaskClient, email: str) -> None:
    response = client.post(
        "/auth/login",
        data={"email": email, "password": PASSWORD},
        headers={"Host": "auth.example.com"},
    )
    assert response.status_code == 302


def get(client: FlaskClient, path: str) -> TestResponse:
    return client.get(path, headers={"Host": "auth.example.com"})


def test_platform_policy_rejects_normal_user(app: Flask) -> None:
    del app
    data = seed_authorization_data()
    user = data["admin"]
    assert isinstance(user, User)

    assert can_access_platform(
        user,
        tenant=None,
        is_platform_request=True,
    ) is False


def test_platform_admin_decorator_rejects_normal_user(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    user = data["admin"]
    assert isinstance(user, User)
    with client.session_transaction(
        environ_overrides={"HTTP_HOST": "platform.yapibina.com"}
    ) as user_session:
        user_session["_user_id"] = str(user.id)
        user_session["_fresh"] = True

    response = client.get(
        "/test/platform-admin",
        headers={"Host": "platform.yapibina.com"},
    )

    assert response.status_code == 403


def test_organization_admin_decorator_rejects_member(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    seed_authorization_data()
    login(client, "manager@example.com")

    response = get(client, "/test/organization-admin")

    assert response.status_code == 403


def test_organization_admin_can_access_own_building(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    login(client, "admin@example.com")
    building = data["other_building"]
    assert isinstance(building, Building)

    response = get(client, f"/test/buildings/{building.id}")

    assert response.status_code == 200


def test_building_manager_only_accesses_assigned_building(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    login(client, "manager@example.com")
    assigned = data["first_building"]
    unassigned = data["other_building"]
    assert isinstance(assigned, Building)
    assert isinstance(unassigned, Building)

    assert get(client, f"/test/buildings/{assigned.id}").status_code == 200
    assert get(client, f"/test/buildings/{unassigned.id}").status_code == 403


def test_cross_tenant_building_id_returns_404(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    login(client, "manager@example.com")
    building = data["cross_building"]
    assert isinstance(building, Building)

    response = get(client, f"/test/buildings/{building.id}")

    assert response.status_code == 404


def test_resident_only_accesses_active_apartment_membership(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    login(client, "resident@example.com")
    own = data["own_apartment"]
    other = data["other_apartment"]
    assert isinstance(own, Apartment)
    assert isinstance(other, Apartment)

    assert get(client, f"/test/apartments/{own.id}").status_code == 200
    assert get(client, f"/test/apartments/{other.id}").status_code == 403


def test_cross_tenant_apartment_id_returns_404(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    login(client, "resident@example.com")
    apartment = data["cross_apartment"]
    assert isinstance(apartment, Apartment)

    response = get(client, f"/test/apartments/{apartment.id}")

    assert response.status_code == 404


def test_expired_apartment_membership_is_rejected(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    data = seed_authorization_data()
    membership = data["apartment_membership"]
    apartment = data["own_apartment"]
    assert isinstance(membership, ApartmentMembership)
    assert isinstance(apartment, Apartment)
    membership.ends_at = utc_now() - timedelta(seconds=1)
    db.session.commit()
    login(client, "resident@example.com")

    response = get(client, f"/test/apartments/{apartment.id}")

    assert response.status_code == 403


def test_invalid_resource_uuid_returns_404(
    app: Flask,
    client: FlaskClient,
) -> None:
    register_test_routes(app)
    seed_authorization_data()
    login(client, "admin@example.com")

    response = get(client, f"/test/buildings/{uuid.uuid4()}")

    assert response.status_code == 404
