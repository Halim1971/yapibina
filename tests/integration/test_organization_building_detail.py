from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import event, select

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
from app.services.organization_apartment_detail import (
    get_organization_apartment_detail,
)
from app.services.organization_building_detail import (
    get_organization_building_detail,
)
from app.services.organization_resident_detail import (
    get_organization_resident_detail,
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


def test_apartment_detail_financial_semantics_and_running_balance() -> None:
    organization, admin = _scope()
    building = _building(organization, "Daire Detay Binası", "DD")
    apartment = _apartment(organization, building, "1")
    _resident(
        organization,
        apartment,
        email="resident-detail@example.com",
        first_name="Deniz",
        last_name="Yalın",
    )
    old_charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Haziran borcu",
        description="Önceki dönem",
        amount="100.00",
        due_date=date(2026, 6, 10),
        created_by_user_id=admin.id,
    )
    current_charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title="Temmuz aidatı",
        description=None,
        amount="200.00",
        due_date=date(2026, 8, 1),
        period_year=2026,
        period_month=7,
        created_by_user_id=admin.id,
    )
    first_payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="150.00",
        payment_date=date(2026, 7, 5),
        payment_method=PaymentMethod.BANK_TRANSFER,
        recorded_by_user_id=admin.id,
        reference="REF-1",
    )
    allocations = auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=first_payment.id,
    )
    unallocated = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="75.00",
        payment_date=date(2026, 7, 20),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
        description="Kullanılmamış ödeme",
    )
    db.session.commit()

    detail = get_organization_apartment_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        timezone_name="Europe/Istanbul",
        reference_date=JULY,
    )
    assert detail.identity.label == "DD-1"
    assert detail.residents[0].display_name == "Deniz Yalın"
    assert detail.financial.total_charges == Decimal("300.00")
    assert detail.financial.total_payments == Decimal("225.00")
    assert detail.financial.total_allocated == Decimal("150.00")
    assert detail.financial.total_unallocated == Decimal("75.00")
    assert detail.financial.outstanding_debt == Decimal("150.00")
    assert detail.financial.current_month_charges == Decimal("200.00")
    assert detail.financial.current_month_payments == Decimal("225.00")
    assert detail.financial.collection_rate == Decimal("112.50")
    assert detail.financial.last_charge_date == date(2026, 8, 1)
    assert detail.financial.last_payment_date == date(2026, 7, 20)
    assert detail.financial.last_payment_amount == unallocated.amount
    assert len(detail.charges.items) == 2
    old_item = next(item for item in detail.charges.items if item.id == old_charge.id)
    current_item = next(
        item for item in detail.charges.items if item.id == current_charge.id
    )
    assert old_item.status_label == "Ödendi"
    assert current_item.status_label == "Kısmi Ödendi"
    assert detail.payments.total == 2
    unused_item = next(
        item for item in detail.payments.items if item.id == unallocated.id
    )
    assert unused_item.unallocated_amount == Decimal("75.00")
    assert sum(
        (item.credit for item in detail.movements.items),
        start=Decimal("0.00"),
    ) == Decimal("150.00")
    chronological = tuple(reversed(detail.movements.items))
    assert chronological[-1].running_balance == detail.financial.outstanding_debt
    assert len(allocations) == 2


def test_apartment_detail_route_scope_authorization_and_building_link(
    client: FlaskClient,
) -> None:
    organization, admin = _scope()
    building = _building(organization, "Route Binası", "ROUTE")
    apartment = _apartment(organization, building, "1")
    other_building = _building(organization, "Diğer Bina", "DIGER")
    other = _organization("apartment-other", "apartment-other.example.com")
    foreign_building = _building(other, "Yabancı Bina", "YBN")
    foreign_apartment = _apartment(other, foreign_building, "9")
    member = _user("apartment-detail-member@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    manager = _user("apartment-detail-manager@example.com")
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
    resident = _resident(
        organization,
        apartment,
        email="apartment-route-resident@example.com",
        first_name="Route",
        last_name="Resident",
    )
    db.session.commit()
    url = f"/organization/buildings/{building.id}/apartments/{apartment.id}"
    assert client.get(url, headers={"Host": HOST}).status_code == 302
    _login(client, admin)
    response = client.get(url, headers={"Host": HOST})
    assert response.status_code == 200
    assert b"Daire ROUTE-1" in response.data
    building_response = client.get(
        f"/organization/buildings/{building.id}",
        headers={"Host": HOST},
    )
    assert url.encode() in building_response.data
    assert (
        client.get(
            f"/organization/buildings/{other_building.id}/apartments/{apartment.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/organization/buildings/{building.id}/apartments/{foreign_apartment.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/organization/buildings/{foreign_building.id}/apartments/{foreign_apartment.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    assert "Yabancı Bina".encode() not in response.data
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, member)
    assert client.get(url, headers={"Host": HOST}).status_code == 403
    assert client.get(url, headers={"Host": "test.local"}).status_code == 403
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, manager)
    assert client.get(url, headers={"Host": HOST}).status_code == 403
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, resident)
    assert client.get(url, headers={"Host": HOST}).status_code == 403


def test_apartment_detail_filters_pagination_and_query_budget() -> None:
    organization, admin = _scope()
    building = _building(organization, "Geçmiş Binası", "GEC")
    apartment = _apartment(organization, building, "1")
    for number in range(25):
        create_manual_charge(
            db.session,
            organization_id=organization.id,
            building_id=building.id,
            apartment_id=apartment.id,
            charge_type=ChargeType.MANUAL,
            title=f"Kayıt {number:02d}",
            description="Aranabilir açıklama" if number == 7 else None,
            amount=str(100 + number),
            due_date=date(2026, 7, (number % 28) + 1),
            created_by_user_id=admin.id,
        )
        record_payment(
            db.session,
            organization_id=organization.id,
            building_id=building.id,
            apartment_id=apartment.id,
            amount=str(50 + number),
            payment_date=date(2026, 7, (number % 28) + 1),
            payment_method=PaymentMethod.CASH,
            recorded_by_user_id=admin.id,
            reference=f"PAY-{number:02d}",
        )
    db.session.commit()
    filtered = get_organization_apartment_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        timezone_name="Europe/Istanbul",
        charge_search="aranabilir",
        payment_search="pay-07",
        charge_sort="outstanding",
        payment_sort="unallocated",
        reference_date=JULY,
    )
    assert filtered.charges.total == 1
    assert filtered.payments.total == 1
    paged = get_organization_apartment_detail(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        timezone_name="Europe/Istanbul",
        charge_page=2,
        payment_page=2,
        charge_per_page=20,
        payment_per_page=20,
        charge_sort="invalid",
        payment_sort="invalid",
        reference_date=JULY,
    )
    assert len(paged.charges.items) == 5
    assert len(paged.payments.items) == 5
    assert paged.charges.sort == "date"
    assert paged.payments.sort == "date"

    query_count = 0

    def count_query(*_: object) -> None:
        nonlocal query_count
        query_count += 1

    engine = db.session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        get_organization_apartment_detail(
            db.session,
            organization_id=organization.id,
            building_id=building.id,
            apartment_id=apartment.id,
            timezone_name="Europe/Istanbul",
            reference_date=JULY,
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_query)
    assert query_count <= 15


def test_resident_detail_reuses_apartment_finance_and_supports_placements() -> None:
    organization, admin = _scope()
    building = _building(organization, "Resident Detay Binası", "RDT")
    apartment = _apartment(organization, building, "1")
    second_apartment = _apartment(organization, building, "2")
    resident = _resident(
        organization,
        apartment,
        email="resident-read-model@example.com",
        first_name="Ece",
        last_name="Sakin",
    )
    other_resident = _resident(
        organization,
        apartment,
        email="shared-home@example.com",
        first_name="Mert",
        last_name="Sakin",
    )
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=second_apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.AUTHORIZED_PERSON,
        )
    )
    charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title="Temmuz aidatı",
        description="Resident detayı finansı",
        amount="200.00",
        due_date=date(2026, 7, 10),
        period_year=2026,
        period_month=7,
        created_by_user_id=admin.id,
    )
    payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="125.00",
        payment_date=date(2026, 7, 12),
        payment_method=PaymentMethod.BANK_TRANSFER,
        recorded_by_user_id=admin.id,
        reference="RESIDENT-PAYMENT",
    )
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    unallocated = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="25.00",
        payment_date=date(2026, 7, 15),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
        description="Kullanılmamış resident ödemesi",
    )
    db.session.commit()

    detail = get_organization_resident_detail(
        db.session,
        organization_id=organization.id,
        resident_id=resident.id,
        selected_apartment_id=apartment.id,
        timezone_name="Europe/Istanbul",
        charge_search="resident detayı",
        payment_search="resident-payment",
    )
    shared = get_organization_resident_detail(
        db.session,
        organization_id=organization.id,
        resident_id=other_resident.id,
        timezone_name="Europe/Istanbul",
    )
    assert detail.resident.display_name == "Ece Sakin"
    assert len(detail.placements) == 2
    assert detail.selected_placement is not None
    assert detail.selected_placement.apartment_id == apartment.id
    assert detail.apartment_finance is not None
    assert detail.apartment_finance.financial.total_charges == Decimal("200.00")
    assert detail.apartment_finance.financial.total_payments == Decimal("150.00")
    assert detail.apartment_finance.financial.total_allocated == Decimal("125.00")
    assert detail.apartment_finance.financial.total_unallocated == Decimal("25.00")
    assert detail.apartment_finance.financial.outstanding_debt == Decimal("75.00")
    assert detail.apartment_finance.financial.current_month_charges == Decimal(
        "200.00"
    )
    assert detail.apartment_finance.financial.current_month_payments == Decimal(
        "150.00"
    )
    assert detail.apartment_finance.financial.collection_rate == Decimal("75.00")
    assert detail.apartment_finance.charges.items[0].id == charge.id
    assert detail.apartment_finance.payments.items[0].id == payment.id
    assert (
        tuple(reversed(detail.apartment_finance.movements.items))[
            -1
        ].running_balance
        == detail.apartment_finance.financial.outstanding_debt
    )
    assert all(
        movement.source_id != unallocated.id
        for movement in detail.apartment_finance.movements.items
    )
    assert shared.apartment_finance is not None
    assert (
        shared.apartment_finance.financial.outstanding_debt
        == detail.apartment_finance.financial.outstanding_debt
    )

    inactive = _resident(
        organization,
        second_apartment,
        email="inactive-placement@example.com",
        first_name="Pasif",
        last_name="Yerleşim",
    )
    membership = db.session.scalar(
        select(ApartmentMembership).where(
            ApartmentMembership.organization_id == organization.id,
            ApartmentMembership.user_id == inactive.id,
        )
    )
    assert membership is not None
    membership.is_active = False
    membership.ends_at = membership.starts_at
    db.session.commit()
    empty = get_organization_resident_detail(
        db.session,
        organization_id=organization.id,
        resident_id=inactive.id,
        timezone_name="Europe/Istanbul",
    )
    assert empty.placements == ()
    assert empty.apartment_finance is None

    query_count = 0

    def count_query(*_: object) -> None:
        nonlocal query_count
        query_count += 1

    engine = db.session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        get_organization_resident_detail(
            db.session,
            organization_id=organization.id,
            resident_id=resident.id,
            selected_apartment_id=apartment.id,
            timezone_name="Europe/Istanbul",
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_query)
    assert query_count <= 15


def test_resident_detail_route_authorization_and_tenant_isolation(
    client: FlaskClient,
) -> None:
    organization, admin = _scope()
    building = _building(organization, "Resident Route Binası", "RRB")
    apartment = _apartment(organization, building, "1")
    resident = _resident(
        organization,
        apartment,
        email="resident-route-target@example.com",
        first_name="Hedef",
        last_name="Resident",
    )
    member = _user("resident-detail-member@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=apartment.id,
            user_id=member.id,
            role=ApartmentMembershipRole.RESIDENT,
        )
    )
    manager = _user("resident-detail-manager@example.com")
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
    foreign = _organization("resident-foreign", "resident-foreign.example.com")
    foreign_building = _building(foreign, "Gizli Resident Binası", "GRB")
    foreign_apartment = _apartment(foreign, foreign_building, "9")
    foreign_resident = _resident(
        foreign,
        foreign_apartment,
        email="foreign-resident-secret@example.com",
        first_name="Gizli",
        last_name="Kişi",
    )
    db.session.commit()
    url = f"/organization/residents/{resident.id}"

    assert client.get(url, headers={"Host": HOST}).status_code == 302
    _login(client, admin)
    response = client.get(url, headers={"Host": HOST})
    assert response.status_code == 200
    assert b"Hedef Resident" in response.data
    assert b"Resident Detay\xc4\xb1" in client.get(
        f"/organization/buildings/{building.id}/apartments/{apartment.id}",
        headers={"Host": HOST},
    ).data
    assert (
        client.get(
            f"/organization/residents/{foreign_resident.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{url}?apartment_id={foreign_apartment.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    assert b"foreign-resident-secret" not in response.data
    assert "Gizli Resident Binası".encode() not in response.data
    assert client.get(url, headers={"Host": "test.local"}).status_code == 403

    for denied_user in (member, manager, resident):
        client.post("/auth/logout", headers={"Host": HOST})
        _login(client, denied_user)
        assert client.get(url, headers={"Host": HOST}).status_code == 403
