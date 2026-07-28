from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from app.extensions import db
from app.models import (
    ApartmentMembershipRole,
    Building,
    BuildingMembershipRole,
    Organization,
    OrganizationMembershipRole,
    User,
)
from app.services import MembershipOverlapError, ServiceValidationError, TenantBoundaryError
from app.services.memberships import (
    create_apartment_membership,
    create_building_membership,
    create_organization_membership,
)
from app.services.organizations import create_apartment


def seed_core() -> tuple[Organization, Organization, Building, Building, User]:
    first_org = Organization(name="First", slug="first")
    second_org = Organization(name="Second", slug="second")
    user = User(
        email="member@example.com",
        password_hash="hash",
        first_name="Member",
        last_name="User",
    )
    db.session.add_all([first_org, second_org, user])
    db.session.flush()
    first_building = Building(
        organization_id=first_org.id,
        name="First Building",
        code="A",
    )
    second_building = Building(
        organization_id=second_org.id,
        name="Second Building",
        code="A",
    )
    db.session.add_all([first_building, second_building])
    db.session.flush()
    return first_org, second_org, first_building, second_building, user


def test_cross_tenant_building_membership_is_rejected(app: Flask) -> None:
    del app
    first_org, _, _, second_building, user = seed_core()

    with pytest.raises(TenantBoundaryError):
        create_building_membership(
            db.session,
            organization_id=first_org.id,
            building_id=second_building.id,
            user_id=user.id,
            role=BuildingMembershipRole.BUILDING_MANAGER,
        )


def test_cross_tenant_apartment_creation_is_rejected(app: Flask) -> None:
    del app
    first_org, _, _, second_building, _ = seed_core()

    with pytest.raises(TenantBoundaryError):
        create_apartment(
            db.session,
            organization_id=first_org.id,
            building_id=second_building.id,
            number="1",
            unit_code="1",
        )


def test_cross_tenant_apartment_membership_is_rejected(app: Flask) -> None:
    del app
    first_org, second_org, _, second_building, user = seed_core()
    apartment = create_apartment(
        db.session,
        organization_id=second_org.id,
        building_id=second_building.id,
        number="1",
        unit_code="1",
    )
    db.session.flush()

    with pytest.raises(TenantBoundaryError):
        create_apartment_membership(
            db.session,
            organization_id=first_org.id,
            apartment_id=apartment.id,
            user_id=user.id,
            role=ApartmentMembershipRole.RESIDENT,
        )


def test_invalid_membership_period_is_rejected(app: Flask) -> None:
    del app
    organization, _, _, _, user = seed_core()
    start = datetime.now(timezone.utc)

    with pytest.raises(ServiceValidationError, match="precede"):
        create_organization_membership(
            db.session,
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            starts_at=start,
            ends_at=start - timedelta(days=1),
        )


def test_inactive_and_expired_memberships_are_not_effective(app: Flask) -> None:
    del app
    organization, _, _, _, user = seed_core()
    now = datetime.now(timezone.utc)
    membership = create_organization_membership(
        db.session,
        organization_id=organization.id,
        user_id=user.id,
        role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        starts_at=now - timedelta(days=10),
        ends_at=now - timedelta(days=1),
    )
    assert membership.is_effective(now) is False

    membership.ends_at = None
    membership.is_active = False
    assert membership.is_effective(now) is False


def test_overlapping_apartment_membership_is_rejected_and_history_allowed(
    app: Flask,
) -> None:
    del app
    organization, _, building, _, user = seed_core()
    apartment = create_apartment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        number="1",
        unit_code="1",
    )
    db.session.flush()
    first_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    first_end = datetime(2025, 6, 30, tzinfo=timezone.utc)
    first = create_apartment_membership(
        db.session,
        organization_id=organization.id,
        apartment_id=apartment.id,
        user_id=user.id,
        role=ApartmentMembershipRole.TENANT,
        starts_at=first_start,
        ends_at=first_end,
    )
    db.session.flush()

    with pytest.raises(MembershipOverlapError):
        create_apartment_membership(
            db.session,
            organization_id=organization.id,
            apartment_id=apartment.id,
            user_id=user.id,
            role=ApartmentMembershipRole.TENANT,
            starts_at=first_end - timedelta(days=1),
        )

    first.is_active = False
    second = create_apartment_membership(
        db.session,
        organization_id=organization.id,
        apartment_id=apartment.id,
        user_id=user.id,
        role=ApartmentMembershipRole.TENANT,
        starts_at=first_end + timedelta(days=1),
    )

    assert first.ends_at is not None
    assert second.starts_at > first.ends_at
