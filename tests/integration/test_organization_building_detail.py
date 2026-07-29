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
    PaymentMethod,
    User,
)
from app.services.charges import create_manual_charge
from app.services.organization_building_detail import (
    get_organization_building_detail,
)
from app.services.payments import auto_allocate_payment, record_payment

HOST = "detail.example.com"
PASSWORD = "SecurePass123"
JULY = date(2026, 7, 20)


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def _user(email: str, first_name: str = "Detay", last_name: str = "Kullanıcı") -> User:
    user = User(
        email=email,
        password_hash="",
        first_name=first_name,
        last_name=last_name,
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


def _scope() -> tuple[Organization, User]:
    organization = _organization("detail", HOST)
    admin = _user("detail-admin@example.com")
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
    code: str,
) -> Building:
    building = Building(
        organization_id=organization.id,
        name=name,
        code=code,
        address_line="Örnek Caddesi 10",
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
        floor=number,
        block="A",
    )
    db.session.add(apartment)
    db.session.flush()
    return apartment


def _resident(
    organization: Organization,
    apartment: Apartment,
    *,
    email: str,
    first_name: str,
    last_name: str,
) -> User:
    resident = _user(email, first_name, last_name)
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
            apartment_id=apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.RESIDENT,
        )
    )
    db.session.flush()
    return resident


def _login(client: FlaskClient, user: User, host: str = HOST) -> None:
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": PASSWORD},
        headers={"Host": host},
    )
    assert response.status_code == 302


def test_building_detail_authorization_and_cross_tenant_404(
    client: FlaskClient,
) -> None:
    organization, admin = _scope()
    building = _building(organization, "Detay Apartmanı", "DETAY")
    other = _organization("other-detail", "other-detail.example.com")
    hidden = _building(other, "Gizli Bina", "GIZLI")
    manager = _user("detail-manager@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=manager.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.add(
        BuildingMembership(
            organization_id=organization.id,
            building_id=building.id,
            user_id=manager.id,
            role=BuildingMembershipRole.BUILDING_MANAGER,
        )
    )
    plain_member = _user("detail-member@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=plain_member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    resident_apartment = _apartment(organization, building, "1")
    resident = _resident(
        organization,
        resident_apartment,
        email="detail-resident@example.com",
        first_name="Resident",
        last_name="Kullanıcı",
    )
    db.session.commit()

    assert (
        client.get(
            f"/organization/buildings/{building.id}",
            headers={"Host": HOST},
        ).status_code
        == 302
    )
    _login(client, admin)
    response = client.get(
        f"/organization/buildings/{building.id}",
        headers={"Host": HOST},
    )
    assert response.status_code == 200
    assert "Detay Apartmanı".encode() in response.data
    assert (
        client.get(
            f"/organization/buildings/{hidden.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, manager)
    assert (
        client.get(
            f"/organization/buildings/{building.id}",
            headers={"Host": HOST},
        ).status_code
        == 403
    )
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, plain_member)
    assert (
        client.get(
            f"/organization/buildings/{building.id}",
            headers={"Host": HOST},
        ).status_code
        == 403
    )
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, resident)
    assert (
        client.get(
            f"/organization/buildings/{building.id}",
            headers={"Host": HOST},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/organization/buildings/{building.id}",
            headers={"Host": "test.local"},
        ).status_code
        == 403
    )


def test_building_detail_metrics_residents_payments_and_movements() -> None:
    organization, admin = _scope()
    building = _building(organization, "Finans Apartmanı", "FIN")
    apartment = _apartment(organization, building, "1")
    empty_apartment = _apartment(organization, building, "2")
    resident = _resident(
        organization,
        apartment,
        email="ayse-yilmaz@example.com",
        first_name="Ayşe",
        last_name="Yılmaz",
    )
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.AUTHORIZED_PERSON,
        )
    )
    current_charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title="Temmuz aidatı",
        description=None,
        amount="100.00",
        due_date=date(2026, 7, 1),
        created_by_user_id=admin.id,
        period_year=2026,
        period_month=7,
    )
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Eski borç",
        description=None,
        amount="50.00",
        due_date=date(2026, 6, 1),
        created_by_user_id=admin.id,
    )
    allocated = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="40.00",
        payment_date=date(2026, 7, 5),
        payment_method=PaymentMethod.BANK_TRANSFER,
        recorded_by_user_id=admin.id,
    )
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=allocated.id,
    )
    latest = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="200.00",
        payment_date=date(2026, 7, 18),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
    )
    record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="25.00",
        payment_date=date(2026, 6, 30),
        payment_method=PaymentMethod.CARD,
        recorded_by_user_id=admin.id,
    )
    other_building = _building(organization, "Başka Bina", "BASKA")
    other_apartment = _apartment(organization, other_building, "9")
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=other_building.id,
        apartment_id=other_apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Görünmemeli",
        description=None,
        amount="999.00",
        due_date=date(2026, 7, 1),
        created_by_user_id=admin.id,
    )
    db.session.commit()

    detail = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        reference_date=JULY,
    )
    assert detail.building.apartment_count == 2
    assert detail.building.active_resident_count == 1
    assert detail.building.outstanding_debt == Decimal("110.00")
    assert detail.building.current_month_charges == Decimal("100.00")
    assert detail.building.current_month_payments == Decimal("240.00")
    assert detail.building.collection_rate == Decimal("240.00")
    assert detail.building.last_financial_movement_date == date(2026, 7, 18)
    assert len(detail.apartments.items) == 2
    first = next(item for item in detail.apartments.items if item.id == apartment.id)
    second = next(
        item for item in detail.apartments.items if item.id == empty_apartment.id
    )
    assert first.resident_summary == "Ayşe Yılmaz"
    assert first.active_resident_count == 1
    assert first.outstanding_debt == Decimal("110.00")
    assert first.current_month_charges == Decimal("100.00")
    assert first.current_month_payments == Decimal("240.00")
    assert first.last_payment_date == latest.payment_date
    assert first.last_payment_amount == Decimal("200.00")
    assert second.resident_summary == "Resident yok"
    assert {movement.kind for movement in detail.movements} == {"Borç", "Ödeme"}
    assert all(movement.description != "Görünmemeli" for movement in detail.movements)
    assert detail.movements[0].movement_date == date(2026, 7, 18)
    assert current_charge.id is not None


def test_building_detail_search_sort_pagination_and_query_budget() -> None:
    organization, _admin = _scope()
    building = _building(organization, "Çok Daireli Bina", "COK")
    apartments = [
        _apartment(organization, building, str(number)) for number in range(1, 26)
    ]
    _resident(
        organization,
        apartments[4],
        email="mehmet-kaya@example.com",
        first_name="Mehmet",
        last_name="Kaya",
    )
    other = _organization("foreign-detail", "foreign-detail.example.com")
    foreign_building = _building(other, "Yabancı Bina", "YAB")
    foreign_apartment = _apartment(other, foreign_building, "99")
    _resident(
        other,
        foreign_apartment,
        email="aranmamali@example.com",
        first_name="Mehmet",
        last_name="Kaya",
    )
    db.session.commit()

    by_name = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        search="  COK-5 ",
        reference_date=JULY,
    )
    assert [item.id for item in by_name.apartments.items] == [apartments[4].id]
    by_resident = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        search="mEhMeT",
        reference_date=JULY,
    )
    assert [item.id for item in by_resident.apartments.items] == [apartments[4].id]
    no_result = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        search="aranmamali",
        reference_date=JULY,
    )
    assert no_result.apartments.total == 0

    first_page = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        sort="invalid",
        direction="invalid",
        page=-2,
        per_page=7,
        reference_date=JULY,
    )
    second_page = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        page=2,
        per_page=20,
        reference_date=JULY,
    )
    assert first_page.apartments.page == 1
    assert first_page.apartments.per_page == 20
    assert first_page.apartments.sort == "apartment"
    assert len(first_page.apartments.items) == 20
    assert len(second_page.apartments.items) == 5
    assert not (
        {item.id for item in first_page.apartments.items}
        & {item.id for item in second_page.apartments.items}
    )

    query_count = 0

    def count_query(*_: object) -> None:
        nonlocal query_count
        query_count += 1

    engine = db.session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        get_organization_building_detail(
            db.session,
            organization_id=organization.id,
            building_id=building.id,
            timezone_name="Europe/Istanbul",
            sort="last_payment",
            direction="desc",
            per_page=50,
            reference_date=JULY,
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_query)
    assert query_count <= 10


def test_building_detail_zero_charge_rate_and_negative_debt_clamp() -> None:
    organization, admin = _scope()
    building = _building(organization, "Boş Finans", "BOS")
    apartment = _apartment(organization, building, "1")
    payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="50.00",
        payment_date=date(2026, 7, 10),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
    )
    db.session.commit()

    detail = get_organization_building_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        timezone_name="Europe/Istanbul",
        reference_date=JULY,
    )
    assert detail.building.collection_rate is None
    assert detail.building.outstanding_debt == Decimal("0.00")
    assert detail.apartments.items[0].outstanding_debt == Decimal("0.00")
    assert detail.apartments.items[0].last_payment_amount == payment.amount
