from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.extensions import db
from app.models import (
    Apartment,
    ApartmentMembershipRole,
    Building,
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
from app.services import (
    DuplicateEntityError,
    InvalidStateTransitionError,
    MembershipOverlapError,
    ServiceValidationError,
    TenantBoundaryError,
)
from app.services.domain_management import (
    create_domain,
    make_primary,
    transition_domain,
)
from app.services.organization_management import (
    create_apartment,
    create_building,
    update_apartment,
    update_building,
)
from app.services.platform_management import (
    create_organization,
    update_branding,
    update_organization,
)
from app.services.user_management import (
    assign_apartment_membership,
    assign_building_membership,
    assign_organization_membership,
    deactivate_membership,
    resolve_or_create_user,
)


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def add_user(email: str, *, platform: bool = False) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="Test",
        last_name="User",
        is_platform_super_admin=platform,
    )
    user.set_password("SecurePass123")
    db.session.add(user)
    db.session.flush()
    return user


def add_organization(slug: str, *, hostname: str | None = None) -> Organization:
    organization = Organization(
        name=slug.title(),
        slug=slug,
        status=OrganizationStatus.ACTIVE,
    )
    db.session.add(organization)
    db.session.flush()
    if hostname:
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


def login(client: FlaskClient, email: str, host: str) -> None:
    response = client.post(
        "/auth/login",
        data={"email": email, "password": "SecurePass123"},
        headers={"Host": host},
    )
    assert response.status_code == 302


def set_authenticated_session(
    client: FlaskClient,
    user: User,
    host: str,
) -> None:
    with client.session_transaction(headers={"Host": host}) as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def seed_platform_admin() -> User:
    user = add_user("platform@example.com", platform=True)
    db.session.commit()
    return user


def seed_tenant_admin(hostname: str = "manage.example.com") -> tuple[Organization, User]:
    organization = add_organization("manage", hostname=hostname)
    user = add_user("admin@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    )
    db.session.commit()
    return organization, user


def test_platform_routes_require_platform_admin(client: FlaskClient) -> None:
    ordinary = add_user("ordinary@example.com")
    db.session.commit()
    set_authenticated_session(client, ordinary, "test.local")
    response = client.get("/platform/organizations", headers={"Host": "test.local"})
    assert response.status_code == 403


def test_platform_admin_lists_and_creates_organization(client: FlaskClient) -> None:
    seed_platform_admin()
    login(client, "platform@example.com", "test.local")
    response = client.get("/platform/organizations", headers={"Host": "test.local"})
    assert response.status_code == 200
    response = client.post(
        "/platform/organizations/new",
        data={"name": "Yeni Firma", "slug": " Yeni Firma ", "status": "active"},
        headers={"Host": "test.local"},
    )
    assert response.status_code == 302
    organization = db.session.scalar(select(Organization).where(Organization.slug == "yeni-firma"))
    assert organization is not None
    assert organization.branding is not None


def test_platform_route_rejects_tenant_hostname(client: FlaskClient) -> None:
    organization = add_organization("tenant", hostname="tenant.example.com")
    admin = add_user("platform-tenant@example.com", platform=True)
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=admin.id,
            role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    )
    db.session.commit()
    set_authenticated_session(client, admin, "tenant.example.com")
    response = client.get("/platform/organizations", headers={"Host": "tenant.example.com"})
    assert response.status_code == 403


def test_duplicate_slug_is_rejected() -> None:
    add_organization("duplicate")
    with pytest.raises(DuplicateEntityError):
        create_organization(
            db.session,
            name="Duplicate",
            legal_name=None,
            slug="duplicate",
            status=OrganizationStatus.ACTIVE,
            support_email=None,
            phone=None,
            website=None,
        )


def test_organization_can_be_updated_without_deletion() -> None:
    organization = add_organization("before")
    update_organization(
        db.session,
        organization_id=organization.id,
        name="After",
        legal_name=None,
        slug="after",
        status=OrganizationStatus.CLOSED,
        support_email=None,
        phone=None,
        website=None,
    )
    assert organization.name == "After"
    assert organization.status is OrganizationStatus.CLOSED


def test_branding_update_and_blank_theme_fallback() -> None:
    organization = add_organization("brand")
    branding = update_branding(
        db.session,
        organization_id=organization.id,
        company_display_name="Brand",
        primary_color=None,
        secondary_color="#abcdef",
        surface_color=None,
        panel_title=None,
        login_message=None,
        white_label_enabled=True,
    )
    assert branding.primary_color is None
    assert branding.secondary_color == "#abcdef"


def test_branding_form_rejects_invalid_hex(client: FlaskClient) -> None:
    admin = seed_platform_admin()
    organization = add_organization("brand-form")
    db.session.commit()
    login(client, admin.email, "test.local")
    response = client.post(
        f"/platform/organizations/{organization.id}/branding",
        data={"primary_color": "red"},
        headers={"Host": "test.local"},
    )
    assert response.status_code == 200
    assert "Renk #RRGGBB" in response.get_data(as_text=True)


def test_domain_creation_normalizes_and_never_activates() -> None:
    organization = add_organization("domain")
    domain = create_domain(
        db.session,
        organization_id=organization.id,
        hostname="Panel.Example.COM.",
        domain_type=DomainType.CUSTOM_DOMAIN,
        is_primary=True,
    )
    assert domain.hostname == "panel.example.com"
    assert domain.state is DomainState.AWAITING_DNS
    assert not domain.is_active
    assert domain.verification_token


@pytest.mark.parametrize(
    "hostname",
    ["https://example.com", "example.com:443", "example.com/path", "example.com?q=1"],
)
def test_invalid_domain_hostname_is_rejected(hostname: str) -> None:
    organization = add_organization(f"host-{uuid.uuid4().hex[:6]}")
    with pytest.raises(ValueError):
        create_domain(
            db.session,
            organization_id=organization.id,
            hostname=hostname,
            domain_type=DomainType.CUSTOM_DOMAIN,
            is_primary=False,
        )


def test_duplicate_hostname_and_second_primary_are_rejected() -> None:
    first = add_organization("first")
    second = add_organization("second")
    create_domain(
        db.session,
        organization_id=first.id,
        hostname="one.example.com",
        domain_type=DomainType.CUSTOM_DOMAIN,
        is_primary=True,
    )
    with pytest.raises(DuplicateEntityError):
        create_domain(
            db.session,
            organization_id=second.id,
            hostname="one.example.com",
            domain_type=DomainType.CUSTOM_DOMAIN,
            is_primary=False,
        )
    with pytest.raises(DuplicateEntityError):
        create_domain(
            db.session,
            organization_id=first.id,
            hostname="two.example.com",
            domain_type=DomainType.CUSTOM_DOMAIN,
            is_primary=True,
        )


def test_domain_state_machine_accepts_only_explicit_transitions() -> None:
    organization = add_organization("states")
    domain = create_domain(
        db.session,
        organization_id=organization.id,
        hostname="states.example.com",
        domain_type=DomainType.CUSTOM_DOMAIN,
        is_primary=False,
    )
    transition_domain(
        db.session,
        organization_id=organization.id,
        domain_id=domain.id,
        target=DomainState.DNS_VERIFIED,
    )
    transition_domain(
        db.session,
        organization_id=organization.id,
        domain_id=domain.id,
        target=DomainState.SSL_PENDING,
    )
    transition_domain(
        db.session,
        organization_id=organization.id,
        domain_id=domain.id,
        target=DomainState.ACTIVE,
    )
    assert domain.is_active
    with pytest.raises(InvalidStateTransitionError):
        transition_domain(
            db.session,
            organization_id=organization.id,
            domain_id=domain.id,
            target=DomainState.DNS_VERIFIED,
        )


def test_cross_organization_domain_action_is_hidden() -> None:
    first = add_organization("domain-one")
    second = add_organization("domain-two")
    domain = create_domain(
        db.session,
        organization_id=first.id,
        hostname="scoped.example.com",
        domain_type=DomainType.CUSTOM_DOMAIN,
        is_primary=False,
    )
    with pytest.raises(ServiceValidationError):
        make_primary(
            db.session,
            organization_id=second.id,
            domain_id=domain.id,
        )


def test_organization_admin_routes_and_role_check(client: FlaskClient) -> None:
    organization, admin = seed_tenant_admin()
    login(client, admin.email, "manage.example.com")
    assert (
        client.get("/organization/buildings", headers={"Host": "manage.example.com"}).status_code
        == 200
    )
    member = add_user("member-manage@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.commit()
    client.post("/auth/logout", headers={"Host": "manage.example.com"})
    login(client, member.email, "manage.example.com")
    assert (
        client.get("/organization/buildings", headers={"Host": "manage.example.com"}).status_code
        == 403
    )


def test_building_uniqueness_is_tenant_scoped_and_cross_tenant_update_fails() -> None:
    first = add_organization("building-one")
    second = add_organization("building-two")
    building = create_building(
        db.session,
        organization_id=first.id,
        name="A",
        code="A1",
        address_line=None,
        district=None,
        city=None,
        postal_code=None,
        is_active=True,
    )
    create_building(
        db.session,
        organization_id=second.id,
        name="A",
        code="A1",
        address_line=None,
        district=None,
        city=None,
        postal_code=None,
        is_active=True,
    )
    with pytest.raises(DuplicateEntityError):
        create_building(
            db.session,
            organization_id=first.id,
            name="Duplicate",
            code="A1",
            address_line=None,
            district=None,
            city=None,
            postal_code=None,
            is_active=True,
        )
    with pytest.raises(TenantBoundaryError):
        update_building(
            db.session,
            organization_id=second.id,
            building_id=building.id,
            name="No",
            code="X",
            address_line=None,
            district=None,
            city=None,
            postal_code=None,
            is_active=False,
        )


def test_apartment_uniqueness_is_building_scoped_and_cross_tenant_fails() -> None:
    first = add_organization("apartment-one")
    second = add_organization("apartment-two")
    first_building = Building(organization_id=first.id, name="A", code="A")
    second_building = Building(organization_id=second.id, name="B", code="B")
    db.session.add_all([first_building, second_building])
    db.session.flush()
    apartment = create_apartment(
        db.session,
        organization_id=first.id,
        building_id=first_building.id,
        number="1",
        floor=None,
        block=None,
        unit_code="U1",
        is_active=True,
    )
    create_apartment(
        db.session,
        organization_id=second.id,
        building_id=second_building.id,
        number="1",
        floor=None,
        block=None,
        unit_code="U1",
        is_active=True,
    )
    with pytest.raises(DuplicateEntityError):
        create_apartment(
            db.session,
            organization_id=first.id,
            building_id=first_building.id,
            number="2",
            floor=None,
            block=None,
            unit_code="U1",
            is_active=True,
        )
    with pytest.raises(TenantBoundaryError):
        update_apartment(
            db.session,
            organization_id=second.id,
            apartment_id=apartment.id,
            number="2",
            floor=None,
            block=None,
            unit_code="U2",
            is_active=False,
        )


def test_user_resolution_reuses_global_user_and_enforces_password_policy() -> None:
    existing = add_user("reuse@example.com")
    resolved, created = resolve_or_create_user(
        db.session,
        email=" REUSE@example.com ",
        first_name="Ignored",
        last_name="Ignored",
        phone=None,
        temporary_password=None,
    )
    assert resolved.id == existing.id
    assert not created
    with pytest.raises(ValueError):
        resolve_or_create_user(
            db.session,
            email="new@example.com",
            first_name="New",
            last_name="User",
            phone=None,
            temporary_password="short",
        )


def test_membership_assignment_and_deactivation_are_scoped() -> None:
    first = add_organization("membership-one")
    second = add_organization("membership-two")
    user = add_user("membership@example.com")
    membership = assign_organization_membership(
        db.session,
        organization_id=first.id,
        user_id=user.id,
        role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
    )
    deactivate_membership(
        db.session,
        organization_id=first.id,
        membership_id=membership.id,
    )
    assert not membership.is_active
    assert membership.ends_at is not None
    with pytest.raises(ServiceValidationError):
        deactivate_membership(
            db.session,
            organization_id=second.id,
            membership_id=membership.id,
        )


def test_building_and_apartment_memberships_reject_cross_tenant() -> None:
    first = add_organization("membership-a")
    second = add_organization("membership-b")
    user = add_user("scoped-member@example.com")
    building = Building(organization_id=first.id, name="A", code="A")
    db.session.add(building)
    db.session.flush()
    apartment = Apartment(
        organization_id=first.id,
        building_id=building.id,
        number="1",
        unit_code="1",
    )
    db.session.add(apartment)
    db.session.flush()
    with pytest.raises(TenantBoundaryError):
        assign_building_membership(
            db.session,
            organization_id=second.id,
            building_id=building.id,
            user_id=user.id,
            role=BuildingMembershipRole.BUILDING_MANAGER,
        )
    with pytest.raises(TenantBoundaryError):
        assign_apartment_membership(
            db.session,
            organization_id=second.id,
            apartment_id=apartment.id,
            user_id=user.id,
            role=ApartmentMembershipRole.RESIDENT,
        )


def test_apartment_membership_overlap_and_historical_reassignment() -> None:
    organization = add_organization("period")
    user = add_user("period@example.com")
    building = Building(organization_id=organization.id, name="A", code="A")
    db.session.add(building)
    db.session.flush()
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="1",
        unit_code="1",
    )
    db.session.add(apartment)
    db.session.flush()
    past = utc_now() - timedelta(days=30)
    assign_apartment_membership(
        db.session,
        organization_id=organization.id,
        apartment_id=apartment.id,
        user_id=user.id,
        role=ApartmentMembershipRole.TENANT,
        starts_at=past,
        ends_at=past + timedelta(days=10),
    )
    current = assign_apartment_membership(
        db.session,
        organization_id=organization.id,
        apartment_id=apartment.id,
        user_id=user.id,
        role=ApartmentMembershipRole.TENANT,
    )
    assert current.is_active
    with pytest.raises(MembershipOverlapError):
        assign_apartment_membership(
            db.session,
            organization_id=organization.id,
            apartment_id=apartment.id,
            user_id=user.id,
            role=ApartmentMembershipRole.OWNER,
        )


def test_invalid_membership_period_is_rejected() -> None:
    organization = add_organization("invalid-period")
    user = add_user("invalid-period@example.com")
    now = utc_now()
    with pytest.raises(ServiceValidationError):
        assign_organization_membership(
            db.session,
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            starts_at=now,
            ends_at=now - timedelta(seconds=1),
        )


def test_management_mutations_are_not_get_routes(
    app: Flask,
    client: FlaskClient,
) -> None:
    admin = seed_platform_admin()
    organization = add_organization("methods")
    domain = OrganizationDomain(
        organization_id=organization.id,
        hostname="methods.example.com",
        domain_type=DomainType.CUSTOM_DOMAIN,
        state=DomainState.ACTIVE,
        is_active=True,
    )
    db.session.add(domain)
    db.session.commit()
    login(client, admin.email, "test.local")
    paths = [
        f"/platform/organizations/{organization.id}/domains/{domain.id}/primary",
        f"/platform/organizations/{organization.id}/domains/{domain.id}/activate",
        f"/platform/organizations/{organization.id}/domains/{domain.id}/suspend",
        f"/organization/memberships/{uuid.uuid4()}/deactivate",
    ]
    for path in paths:
        assert client.get(path, headers={"Host": "test.local"}).status_code == 405


def test_platform_list_pagination_and_search_are_scoped(
    app: Flask,
    client: FlaskClient,
) -> None:
    app.config["MANAGEMENT_PAGE_SIZE"] = 2
    admin = seed_platform_admin()
    for slug in ("alpha", "beta", "gamma"):
        add_organization(slug)
    db.session.commit()
    login(client, admin.email, "test.local")
    first_page = client.get("/platform/organizations?page=1", headers={"Host": "test.local"})
    assert first_page.status_code == 200
    assert "Sonraki" in first_page.get_data(as_text=True)
    search = client.get("/platform/organizations?q=gamma", headers={"Host": "test.local"}).get_data(
        as_text=True
    )
    assert "Gamma" in search
    assert "Alpha" not in search


def test_organization_admin_creates_building_and_apartment(
    client: FlaskClient,
) -> None:
    organization, admin = seed_tenant_admin()
    login(client, admin.email, "manage.example.com")
    response = client.post(
        "/organization/buildings/new",
        data={"name": "Merkez", "code": "M01", "is_active": "y"},
        headers={"Host": "manage.example.com"},
    )
    assert response.status_code == 302
    building = db.session.scalar(
        select(Building).where(
            Building.organization_id == organization.id,
            Building.code == "M01",
        )
    )
    assert building is not None
    response = client.post(
        f"/organization/buildings/{building.id}/apartments/new",
        data={"number": "1", "unit_code": "M01-1", "is_active": "y"},
        headers={"Host": "manage.example.com"},
    )
    assert response.status_code == 302
    apartment = db.session.scalar(
        select(Apartment).where(
            Apartment.organization_id == organization.id,
            Apartment.unit_code == "M01-1",
        )
    )
    assert apartment is not None


def test_organization_admin_cannot_edit_other_tenant_resources(
    client: FlaskClient,
) -> None:
    _, admin = seed_tenant_admin()
    other = add_organization("other-management")
    building = Building(organization_id=other.id, name="Other", code="O1")
    db.session.add(building)
    db.session.flush()
    apartment = Apartment(
        organization_id=other.id,
        building_id=building.id,
        number="1",
        unit_code="O1-1",
    )
    db.session.add(apartment)
    db.session.commit()
    login(client, admin.email, "manage.example.com")
    assert (
        client.get(
            f"/organization/buildings/{building.id}/edit",
            headers={"Host": "manage.example.com"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/organization/apartments/{apartment.id}/edit",
            headers={"Host": "manage.example.com"},
        ).status_code
        == 404
    )


def test_organization_user_creation_and_existing_user_reuse(
    client: FlaskClient,
) -> None:
    organization, admin = seed_tenant_admin()
    existing = add_user("existing-global@example.com")
    db.session.commit()
    login(client, admin.email, "manage.example.com")
    response = client.post(
        "/organization/users/new",
        data={
            "email": "new-tenant@example.com",
            "first_name": "New",
            "last_name": "Tenant",
            "temporary_password": "Temporary123",
            "organization_role": "organization_member",
        },
        headers={"Host": "manage.example.com"},
    )
    assert response.status_code == 302
    response = client.post(
        "/organization/users/new",
        data={
            "email": existing.email,
            "organization_role": "organization_member",
        },
        headers={"Host": "manage.example.com"},
    )
    assert response.status_code == 302
    assert (
        db.session.scalar(
            select(db.func.count(User.id)).where(
                User.email == "existing-global@example.com"
            )
        )
        == 1
    )
    assert db.session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == existing.id,
        )
    )


def test_user_search_never_returns_other_tenant_member(client: FlaskClient) -> None:
    _, admin = seed_tenant_admin()
    other = add_organization("search-other")
    hidden = add_user("hidden@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=other.id,
            user_id=hidden.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.commit()
    login(client, admin.email, "manage.example.com")
    response = client.get(
        "/organization/users?q=hidden",
        headers={"Host": "manage.example.com"},
    )
    assert response.status_code == 200
    assert "hidden@example.com" not in response.get_data(as_text=True)


def test_suspended_organization_management_host_is_rejected(
    client: FlaskClient,
) -> None:
    organization, admin = seed_tenant_admin()
    organization.status = OrganizationStatus.SUSPENDED
    db.session.commit()
    response = client.post(
        "/auth/login",
        data={"email": admin.email, "password": "SecurePass123"},
        headers={"Host": "manage.example.com"},
    )
    assert response.status_code == 421
