from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import event

from app.extensions import db
from app.models import (
    Apartment,
    ApartmentMembership,
    ApartmentMembershipRole,
    Building,
    BuildingMembership,
    BuildingMembershipRole,
    ChargeType,
    DomainState,
    DomainType,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    PaymentAllocation,
    PaymentMethod,
    User,
)
from app.services.charges import create_manual_charge
from app.services.organization_buildings import list_organization_buildings
from app.services.payments import auto_allocate_payment, record_payment

HOST = "buildings.example.com"
PASSWORD = "SecurePass123"
JULY = date(2026, 7, 20)


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def _user(email: str) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="Bina",
        last_name="Kullanıcısı",
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _organization(slug: str, hostname: str) -> Organization:
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
    organization = _organization("buildings", HOST)
    admin = _user("buildings-admin@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=admin.id,
            role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    )
    db.session.commit()
    return organization, admin


def _building(
    organization: Organization,
    name: str,
    *,
    address: str | None = None,
) -> Building:
    building = Building(
        organization_id=organization.id,
        name=name,
        code=name.upper().replace(" ", "-"),
        address_line=address,
        district="Kadıköy",
        city="İstanbul",
    )
    db.session.add(building)
    db.session.flush()
    return building


def _apartment(
    organization: Organization,
    building: Building,
    number: str,
) -> Apartment:
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number=number,
        unit_code=f"{building.code}-{number}",
    )
    db.session.add(apartment)
    db.session.flush()
    return apartment


def _login(client: FlaskClient, user: User) -> None:
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": PASSWORD},
        headers={"Host": HOST},
    )
    assert response.status_code == 302


def test_building_list_access_empty_state_and_tenant_context(
    client: FlaskClient,
) -> None:
    organization, admin = _admin_scope()
    response = client.get("/organization/buildings", headers={"Host": HOST})
    assert response.status_code == 302
    _login(client, admin)
    response = client.get("/organization/buildings", headers={"Host": HOST})
    assert response.status_code == 200
    assert "Henüz bina bulunmuyor.".encode() in response.data
    assert b"Toplam 0 bina" in response.data

    member = _user("buildings-member@example.com")
    assigned_building = _building(organization, "Atanmış Bina")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.add(
        BuildingMembership(
            organization_id=organization.id,
            building_id=assigned_building.id,
            user_id=member.id,
            role=BuildingMembershipRole.BUILDING_MANAGER,
        )
    )
    db.session.commit()
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, member)
    assert (
        client.get("/organization/buildings", headers={"Host": HOST}).status_code
        == 403
    )
    assert (
        client.get("/organization/buildings", headers={"Host": "test.local"}).status_code
        == 403
    )

    plain_member = _user("buildings-plain-member@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=plain_member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.commit()
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, plain_member)
    assert (
        client.get("/organization/buildings", headers={"Host": HOST}).status_code
        == 403
    )


def test_building_metrics_search_sort_and_tenant_isolation() -> None:
    organization, admin = _admin_scope()
    alpha = _building(
        organization,
        "Alfa Apartmanı",
        address="Bagdat Caddesi",
    )
    beta = _building(organization, "Beta Sitesi", address="Rıhtım Sokak")
    alpha_apartment = _apartment(organization, alpha, "1")
    _apartment(organization, alpha, "2")
    _apartment(organization, beta, "1")
    resident = _user("alpha-resident@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=resident.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=alpha_apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.RESIDENT,
        )
    )
    charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=alpha.id,
        apartment_id=alpha_apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Temmuz borcu",
        description=None,
        amount="100.00",
        due_date=date(2026, 7, 1),
        created_by_user_id=admin.id,
    )
    payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=alpha.id,
        apartment_id=alpha_apartment.id,
        amount="40.00",
        payment_date=date(2026, 7, 5),
        payment_method=PaymentMethod.BANK_TRANSFER,
        recorded_by_user_id=admin.id,
    )
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    record_payment(
        db.session,
        organization_id=organization.id,
        building_id=alpha.id,
        apartment_id=alpha_apartment.id,
        amount="500.00",
        payment_date=date(2026, 7, 8),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
    )
    record_payment(
        db.session,
        organization_id=organization.id,
        building_id=alpha.id,
        apartment_id=alpha_apartment.id,
        amount="25.00",
        payment_date=date(2026, 6, 30),
        payment_method=PaymentMethod.CARD,
        recorded_by_user_id=admin.id,
    )

    other = _organization("other-buildings", "other-buildings.example.com")
    hidden = _building(other, "Gizli Bina", address="Bagdat Caddesi")
    hidden_apartment = _apartment(other, hidden, "9")
    create_manual_charge(
        db.session,
        organization_id=other.id,
        building_id=hidden.id,
        apartment_id=hidden_apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Gizli borç",
        description=None,
        amount="9999.00",
        due_date=date(2026, 7, 1),
        created_by_user_id=admin.id,
    )
    db.session.commit()

    listing = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        reference_date=JULY,
    )
    assert listing.total == 2
    assert [item.name for item in listing.items] == [
        "Alfa Apartmanı",
        "Beta Sitesi",
    ]
    alpha_row = listing.items[0]
    assert alpha_row.apartment_count == 2
    assert alpha_row.active_resident_count == 1
    assert alpha_row.outstanding_debt == Decimal("60.00")
    assert alpha_row.current_month_payments == Decimal("540.00")
    assert isinstance(alpha_row.outstanding_debt, Decimal)
    assert all(item.name != "Gizli Bina" for item in listing.items)
    assert all(item.outstanding_debt != Decimal("9999.00") for item in listing.items)

    by_name = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        search="  alfa  ",
        reference_date=JULY,
    )
    assert [item.name for item in by_name.items] == ["Alfa Apartmanı"]
    by_address = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        search="BAGDAT",
        reference_date=JULY,
    )
    assert [item.name for item in by_address.items] == ["Alfa Apartmanı"]
    assert "Gizli Bina" not in [item.name for item in by_address.items]
    no_result = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        search="bulunmaz",
        reference_date=JULY,
    )
    assert no_result.total == 0
    assert no_result.items == ()

    by_apartments = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        sort="apartments",
        direction="desc",
        reference_date=JULY,
    )
    assert by_apartments.items[0].id == alpha.id
    by_debt = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        sort="debt",
        direction="desc",
        reference_date=JULY,
    )
    assert by_debt.items[0].id == alpha.id
    by_payment = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        sort="payments",
        direction="desc",
        reference_date=JULY,
    )
    assert by_payment.items[0].id == alpha.id
    safe_default = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        sort="DROP TABLE",
        direction="sideways",
        reference_date=JULY,
    )
    assert safe_default.sort == "name"
    assert safe_default.direction == "asc"
    assert charge.id is not None


def test_overallocation_is_clamped_to_zero() -> None:
    organization, admin = _admin_scope()
    building = _building(organization, "Borçsuz Bina")
    apartment = _apartment(organization, building, "1")
    charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Borç",
        description=None,
        amount="100.00",
        due_date=date(2026, 7, 1),
        created_by_user_id=admin.id,
    )
    payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="200.00",
        payment_date=date(2026, 7, 2),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
    )
    db.session.add(
        PaymentAllocation(
            organization_id=organization.id,
            payment_id=payment.id,
            charge_id=charge.id,
            amount=Decimal("150.00"),
        )
    )
    db.session.commit()
    listing = list_organization_buildings(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        reference_date=JULY,
    )
    assert listing.items[0].outstanding_debt == Decimal("0.00")


def test_pagination_parameters_and_query_budget(
    app: Flask,
    client: FlaskClient,
) -> None:
    organization, admin = _admin_scope()
    for index in range(25):
        _building(organization, f"Bina {index:02d}")
    db.session.commit()
    organization_id = organization.id
    statements = 0

    def count_statement(*args: object, **kwargs: object) -> None:
        nonlocal statements
        del args, kwargs
        statements += 1

    event.listen(db.engine, "before_cursor_execute", count_statement)
    try:
        first = list_organization_buildings(
            db.session,
            organization_id=organization_id,
            timezone_name="Europe/Istanbul",
            page=-1,
            per_page=17,
            reference_date=JULY,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", count_statement)
    assert first.page == 1
    assert first.per_page == 20
    assert first.total == 25
    assert len(first.items) == 20
    assert statements == 2

    second = list_organization_buildings(
        db.session,
        organization_id=organization_id,
        timezone_name="Europe/Istanbul",
        page=2,
        per_page=20,
        reference_date=JULY,
    )
    assert len(second.items) == 5
    assert {item.id for item in first.items}.isdisjoint(
        {item.id for item in second.items}
    )
    assert len(
        list_organization_buildings(
            db.session,
            organization_id=organization_id,
            timezone_name="Europe/Istanbul",
            per_page=50,
            reference_date=JULY,
        ).items
    ) == 25
    assert (
        list_organization_buildings(
            db.session,
            organization_id=organization_id,
            timezone_name="Europe/Istanbul",
            per_page=100,
            reference_date=JULY,
        ).per_page
        == 100
    )
    _login(client, admin)
    response = client.get(
        "/organization/buildings?q=Bina&sort=debt&direction=desc&per_page=20",
        headers={"Host": HOST},
    )
    assert response.status_code == 200
    assert b"q=Bina" in response.data
    assert b"sort=debt" in response.data
    assert b"direction=desc" in response.data
    assert app is not None
