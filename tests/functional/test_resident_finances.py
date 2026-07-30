from __future__ import annotations

from datetime import date, timedelta
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
    Charge,
    ChargeStatus,
    ChargeType,
    DomainState,
    DomainType,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    User,
    UserStatus,
)
from app.models.base import utc_now
from app.services import EntityNotFoundError
from app.services.charges import create_manual_charge
from app.services.payments import (
    allocate_payment,
    auto_allocate_payment,
    record_payment,
)
from app.services.resident_finances import (
    StatementFilters,
    get_resident_account_statement,
    get_resident_dashboard,
    list_resident_apartments,
)

HOST = "resident.example.com"
PASSWORD = "ResidentPass123"


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def _user(
    email: str,
    *,
    platform: bool = False,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="Test",
        last_name="Sakini",
        status=status,
        is_platform_super_admin=platform,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _organization(
    slug: str,
    hostname: str,
    *,
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> Organization:
    organization = Organization(name=slug.title(), slug=slug, status=status)
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


def _building(
    organization: Organization,
    code: str,
    *,
    active: bool = True,
) -> Building:
    building = Building(
        organization_id=organization.id,
        name=f"{code} Apartmanı",
        code=code,
        is_active=active,
    )
    db.session.add(building)
    db.session.flush()
    return building


def _apartment(
    organization: Organization,
    building: Building,
    code: str,
    *,
    active: bool = True,
) -> Apartment:
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number=code,
        unit_code=code,
        floor="2",
        block="A",
        is_active=active,
    )
    db.session.add(apartment)
    db.session.flush()
    return apartment


def _organization_membership(
    organization: Organization,
    user: User,
    *,
    role: OrganizationMembershipRole = OrganizationMembershipRole.ORGANIZATION_MEMBER,
) -> OrganizationMembership:
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role=role,
        starts_at=utc_now() - timedelta(days=2),
    )
    db.session.add(membership)
    db.session.flush()
    return membership


def _apartment_membership(
    organization: Organization,
    apartment: Apartment,
    user: User,
    *,
    active: bool = True,
    starts_delta: int = -2,
    ends_delta: int | None = None,
) -> ApartmentMembership:
    membership = ApartmentMembership(
        organization_id=organization.id,
        apartment_id=apartment.id,
        user_id=user.id,
        role=ApartmentMembershipRole.RESIDENT,
        is_active=active,
        starts_at=utc_now() + timedelta(days=starts_delta),
        ends_at=(
            utc_now() + timedelta(days=ends_delta)
            if ends_delta is not None
            else None
        ),
    )
    db.session.add(membership)
    db.session.flush()
    return membership


def _seed_resident() -> tuple[Organization, User, Building, Apartment]:
    organization = _organization("sakin", HOST)
    resident = _user("resident@example.com")
    _organization_membership(organization, resident)
    building = _building(organization, "GÜNEŞ")
    apartment = _apartment(organization, building, "A-2")
    _apartment_membership(organization, apartment, resident)
    db.session.commit()
    return organization, resident, building, apartment


def _login(client: FlaskClient, email: str) -> None:
    response = client.post(
        "/auth/login",
        data={"email": email, "password": PASSWORD},
        headers={"Host": HOST},
    )
    assert response.status_code == 302


def _session_login(client: FlaskClient, user: User) -> None:
    with client.session_transaction(headers={"Host": HOST}) as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _charge(
    organization: Organization,
    building: Building,
    apartment: Apartment,
    user: User,
    amount: str,
    *,
    title: str = "Mart 2026 Aidatı",
    due_date: date = date(2026, 3, 15),
) -> Charge:
    return create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title=title,
        description=None,
        amount=amount,
        due_date=due_date,
        created_by_user_id=user.id,
        period_year=due_date.year,
        period_month=due_date.month,
    )


def _payment(
    organization: Organization,
    building: Building,
    apartment: Apartment,
    user: User,
    amount: str,
    *,
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER,
    payment_date: date = date(2026, 3, 20),
) -> Payment:
    return record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount=amount,
        payment_date=payment_date,
        payment_method=method,
        recorded_by_user_id=user.id,
    )


def test_resident_access_and_empty_state(client: FlaskClient) -> None:
    response = client.get("/resident/", headers={"Host": HOST})
    assert response.status_code == 421

    organization = _organization("empty", HOST)
    resident = _user("empty@example.com")
    _organization_membership(organization, resident)
    db.session.commit()
    _login(client, resident.email)
    response = client.get("/resident/", headers={"Host": HOST})
    assert response.status_code == 200
    assert "Henüz hesabınıza bağlı aktif bir daire bulunmuyor.".encode() in response.data


def test_unauthenticated_known_tenant_redirects_to_login(client: FlaskClient) -> None:
    _seed_resident()
    response = client.get("/resident/", headers={"Host": HOST})
    assert response.status_code == 302
    assert "/auth/login" in response.location


def test_admin_and_platform_accounts_do_not_gain_resident_access(
    client: FlaskClient,
) -> None:
    organization = _organization("roles", HOST)
    admin = _user("admin@example.com")
    platform = _user("platform@example.com", platform=True)
    _organization_membership(
        organization,
        admin,
        role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
    )
    _organization_membership(organization, platform)
    db.session.commit()

    _session_login(client, admin)
    assert client.get("/resident/", headers={"Host": HOST}).status_code == 403
    _session_login(client, platform)
    assert client.get("/resident/", headers={"Host": HOST}).status_code == 403


def test_inactive_user_and_suspended_organization_are_rejected(
    client: FlaskClient,
) -> None:
    organization, resident, _, _ = _seed_resident()
    _session_login(client, resident)
    resident.status = UserStatus.INACTIVE
    db.session.commit()
    assert client.get("/resident/", headers={"Host": HOST}).status_code == 302

    resident.status = UserStatus.ACTIVE
    organization.status = OrganizationStatus.SUSPENDED
    db.session.commit()
    _session_login(client, resident)
    assert client.get("/resident/", headers={"Host": HOST}).status_code == 421


@pytest.mark.parametrize(
    ("active", "starts_delta", "ends_delta"),
    [
        (False, -2, None),
        (True, -5, -1),
        (True, 1, None),
    ],
)
def test_ineffective_apartment_membership_returns_empty_state(
    client: FlaskClient,
    active: bool,
    starts_delta: int,
    ends_delta: int | None,
) -> None:
    organization = _organization("period", HOST)
    resident = _user("period@example.com")
    _organization_membership(organization, resident)
    building = _building(organization, "P")
    apartment = _apartment(organization, building, "1")
    _apartment_membership(
        organization,
        apartment,
        resident,
        active=active,
        starts_delta=starts_delta,
        ends_delta=ends_delta,
    )
    db.session.commit()
    _login(client, resident.email)
    response = client.get("/resident/", headers={"Host": HOST})
    assert "Henüz hesabınıza bağlı aktif bir daire bulunmuyor.".encode() in response.data


def test_inactive_apartment_or_building_is_not_available(client: FlaskClient) -> None:
    organization, resident, building, apartment = _seed_resident()
    apartment.is_active = False
    db.session.commit()
    _login(client, resident.email)
    response = client.get("/resident/", headers={"Host": HOST})
    assert "Henüz hesabınıza bağlı aktif bir daire bulunmuyor.".encode() in response.data

    apartment.is_active = True
    building.is_active = False
    db.session.commit()
    response = client.get("/resident/", headers={"Host": HOST})
    assert "Henüz hesabınıza bağlı aktif bir daire bulunmuyor.".encode() in response.data


def test_multiple_apartments_can_be_selected_but_unrelated_one_is_404(
    client: FlaskClient,
) -> None:
    organization, resident, building, first = _seed_resident()
    second = _apartment(organization, building, "A-3")
    unrelated = _apartment(organization, building, "A-4")
    _apartment_membership(organization, second, resident)
    db.session.commit()
    _login(client, resident.email)

    response = client.get("/resident/", headers={"Host": HOST})
    assert b"Daire se\xc3\xa7in" in response.data
    assert b"A-2" in response.data and b"A-3" in response.data
    assert b"A-4" not in response.data
    assert client.get(
        f"/resident/?apartment_id={second.id}",
        headers={"Host": HOST},
    ).status_code == 200
    assert client.get(
        f"/resident/?apartment_id={unrelated.id}",
        headers={"Host": HOST},
    ).status_code == 404
    assert first.id != second.id


def test_single_apartment_does_not_show_picker(client: FlaskClient) -> None:
    _, resident, _, _ = _seed_resident()
    _login(client, resident.email)
    response = client.get("/resident/", headers={"Host": HOST})
    assert b"Daire se\xc3\xa7in" not in response.data


def test_cross_tenant_apartment_cannot_be_selected(client: FlaskClient) -> None:
    _, resident, _, _ = _seed_resident()
    other = _organization("other", "other-resident.example.com")
    other_building = _building(other, "O")
    other_apartment = _apartment(other, other_building, "O-1")
    db.session.commit()
    _login(client, resident.email)
    response = client.get(
        f"/resident/?apartment_id={other_apartment.id}",
        headers={"Host": HOST},
    )
    assert response.status_code == 404


def test_dashboard_debt_partial_payment_and_unallocated_are_separate(
    client: FlaskClient,
) -> None:
    organization, resident, building, apartment = _seed_resident()
    _charge(organization, building, apartment, resident, "1000.00")
    payment = _payment(organization, building, apartment, resident, "700.00")
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    extra = _payment(organization, building, apartment, resident, "200.00")
    db.session.commit()
    _login(client, resident.email)

    response = client.get("/resident/", headers={"Host": HOST})
    assert b"300,00 TL" in response.data
    assert "Kullanılmamış ödeme".encode() in response.data
    assert b"200,00 TL" in response.data
    dashboard = get_resident_dashboard(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
    )
    assert dashboard.current_debt == Decimal("300.00")
    assert dashboard.unallocated_payment == Decimal("200.00")
    assert extra.id is not None


def test_fully_paid_debt_is_zero_and_message_is_friendly(
    client: FlaskClient,
) -> None:
    organization, resident, building, apartment = _seed_resident()
    _charge(organization, building, apartment, resident, "250.00")
    payment = _payment(organization, building, apartment, resident, "250.00")
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    db.session.commit()
    _login(client, resident.email)
    response = client.get("/resident/", headers={"Host": HOST})
    assert b"Borcunuz bulunmuyor." in response.data
    assert b"0,00 TL" in response.data


def test_reversed_records_are_hidden_and_do_not_change_debt(
    client: FlaskClient,
) -> None:
    organization, resident, building, apartment = _seed_resident()
    valid = _charge(organization, building, apartment, resident, "300.00")
    reversed_charge = _charge(
        organization,
        building,
        apartment,
        resident,
        "900.00",
        title="Görünmemesi gereken borç",
    )
    reversed_charge.status = ChargeStatus.REVERSED
    payment = _payment(organization, building, apartment, resident, "100.00")
    payment.status = PaymentStatus.REVERSED
    db.session.commit()
    _login(client, resident.email)

    response = client.get("/resident/", headers={"Host": HOST})
    assert b"300,00 TL" in response.data
    assert "Görünmemesi gereken borç".encode() not in response.data
    assert b"100,00 TL" not in response.data
    assert valid.id is not None


def test_payments_are_user_facing_and_reversed_payment_is_hidden(
    client: FlaskClient,
) -> None:
    organization, resident, building, apartment = _seed_resident()
    _payment(
        organization,
        building,
        apartment,
        resident,
        "125.00",
        method=PaymentMethod.BANK_TRANSFER,
    )
    reversed_payment = _payment(
        organization,
        building,
        apartment,
        resident,
        "999.00",
        method=PaymentMethod.CARD,
    )
    reversed_payment.status = PaymentStatus.REVERSED
    db.session.commit()
    _login(client, resident.email)

    response = client.get("/resident/payments", headers={"Host": HOST})
    assert response.status_code == 200
    assert b"Havale/EFT" in response.data
    assert b"125,00 TL" in response.data
    assert b"999,00 TL" not in response.data
    assert str(reversed_payment.id).encode() not in response.data


def test_empty_payments_message(client: FlaskClient) -> None:
    _, resident, _, _ = _seed_resident()
    _login(client, resident.email)
    response = client.get("/resident/payments", headers={"Host": HOST})
    assert "Henüz kayıtlı bir ödemeniz bulunmuyor.".encode() in response.data


def test_statement_uses_allocated_part_and_has_deterministic_balance(
    client: FlaskClient,
) -> None:
    organization, resident, building, apartment = _seed_resident()
    first = _charge(
        organization,
        building,
        apartment,
        resident,
        "400.00",
        title="Ocak 2026 Aidatı",
        due_date=date(2026, 1, 15),
    )
    second = _charge(
        organization,
        building,
        apartment,
        resident,
        "600.00",
        title="Şubat 2026 Aidatı",
        due_date=date(2026, 2, 15),
    )
    payment = _payment(
        organization,
        building,
        apartment,
        resident,
        "700.00",
        payment_date=date(2026, 2, 20),
    )
    allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
        charge_id=first.id,
        amount="400.00",
    )
    allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
        charge_id=second.id,
        amount="200.00",
    )
    db.session.commit()

    statement = get_resident_account_statement(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
    )
    assert [row.running_balance for row in statement.items] == [
        Decimal("400.00"),
        Decimal("1000.00"),
        Decimal("400.00"),
    ]
    assert statement.items[-1].payment_amount == Decimal("600.00")
    assert len(statement.items) == 3

    _login(client, resident.email)
    response = client.get("/resident/account", headers={"Host": HOST})
    assert response.status_code == 200
    assert "kullanılmamış tutar ayrıca gösterilir".encode() in response.data
    assert b"PaymentAllocation" not in response.data


def test_other_apartment_finances_never_enter_dashboard() -> None:
    organization, resident, building, apartment = _seed_resident()
    other = _apartment(organization, building, "A-99")
    _charge(organization, building, apartment, resident, "100.00")
    _charge(organization, building, other, resident, "9000.00")
    db.session.commit()
    dashboard = get_resident_dashboard(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
    )
    assert dashboard.current_debt == Decimal("100.00")


def test_account_pagination_and_read_only_routes(client: FlaskClient) -> None:
    organization, resident, building, apartment = _seed_resident()
    for index in range(21):
        _charge(
            organization,
            building,
            apartment,
            resident,
            "10.00",
            title=f"{index + 1}. aidat",
            due_date=date(2026, 1, 1) + timedelta(days=index),
        )
    db.session.commit()
    _login(client, resident.email)
    response = client.get("/resident/account?page=2", headers={"Host": HOST})
    assert response.status_code == 200
    assert b"2 / 2" in response.data
    for path in ("/resident/", "/resident/account", "/resident/payments"):
        assert client.post(path, headers={"Host": HOST}).status_code == 405


def test_resident_navigation_and_ui_do_not_expose_technical_terms(
    client: FlaskClient,
) -> None:
    _, resident, _, _ = _seed_resident()
    _login(client, resident.email)
    response = client.get("/resident/", headers={"Host": HOST})
    assert b"Dairem" in response.data
    assert b"Hesap hareketleri" in response.data
    assert b"Binalar" not in response.data
    assert b"resident-summary" in response.data
    for term in (
        b"Charge",
        b"PaymentAllocation",
        b"ChargeBatch",
        b"Tenant",
        b"Membership",
        b"Ledger",
        b"Posted",
        b"Reversed",
    ):
        assert term not in response.data


def test_service_requires_organization_membership() -> None:
    organization = _organization("scope", HOST)
    user = _user("scope@example.com")
    building = _building(organization, "S")
    apartment = _apartment(organization, building, "S-1")
    _apartment_membership(organization, apartment, user)
    db.session.commit()
    with pytest.raises(EntityNotFoundError, match="Resident erişimi bulunamadı"):
        list_resident_apartments(
            db.session,
            organization_id=organization.id,
            user_id=user.id,
        )


def test_statement_filters_and_transport_independent_summary() -> None:
    organization, resident, building, apartment = _seed_resident()
    _charge(
        organization,
        building,
        apartment,
        resident,
        "400.00",
        title="Ocak aidatı",
        due_date=date(2026, 1, 15),
    )
    payment = _payment(
        organization,
        building,
        apartment,
        resident,
        "150.00",
        payment_date=date(2026, 1, 20),
    )
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    db.session.commit()

    statement = get_resident_account_statement(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
        filters=StatementFilters(
            query="ödeme",
            date_from=date(2026, 1, 16),
            date_to=date(2026, 1, 31),
            movement_type="payment",
        ),
    )

    assert len(statement.items) == 1
    assert statement.items[0].payment_amount == Decimal("150.00")
    assert statement.current_balance == Decimal("250.00")
    assert statement.total_charges == Decimal("400.00")
    assert statement.total_payments == Decimal("150.00")
    assert statement.latest_charge_date == date(2026, 1, 15)
    assert statement.latest_payment_date == date(2026, 1, 20)


def test_account_filters_are_rendered_and_preserved(client: FlaskClient) -> None:
    organization, resident, building, apartment = _seed_resident()
    _charge(
        organization,
        building,
        apartment,
        resident,
        "100.00",
        title="Özel açıklamalı aidat",
        due_date=date(2026, 4, 15),
    )
    db.session.commit()
    _login(client, resident.email)

    response = client.get(
        "/resident/account"
        "?q=%C3%96zel&date_from=2026-04-01&date_to=2026-04-30"
        "&type=debt&per_page=50",
        headers={"Host": HOST},
    )

    assert response.status_code == 200
    assert "Özel açıklamalı aidat".encode() in response.data
    assert b'value="2026-04-01"' in response.data
    assert b'value="2026-04-30"' in response.data
    assert b"G\xc3\xbcncel bakiye" in response.data


def test_dashboard_overdue_summary_and_service_query_budget(app: Flask) -> None:
    organization, resident, building, apartment = _seed_resident()
    _charge(
        organization,
        building,
        apartment,
        resident,
        "275.00",
        due_date=date(2026, 1, 15),
    )
    db.session.commit()
    statements = 0

    def count_query(*_: object) -> None:
        nonlocal statements
        statements += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        dashboard = get_resident_dashboard(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            apartment_id=apartment.id,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert dashboard.overdue_debt == Decimal("275.00")
    assert dashboard.latest_charge_date == date(2026, 1, 15)
    assert statements <= 10


def test_finance_statement_query_budget_does_not_grow_with_rows(app: Flask) -> None:
    organization, resident, building, apartment = _seed_resident()
    for index in range(25):
        _charge(
            organization,
            building,
            apartment,
            resident,
            "10.00",
            title=f"Hareket {index}",
            due_date=date(2026, 1, 1) + timedelta(days=index),
        )
    db.session.commit()
    statements = 0

    def count_query(*_: object) -> None:
        nonlocal statements
        statements += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        result = get_resident_account_statement(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            apartment_id=apartment.id,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert result.total_items == 25
    assert statements <= 8
