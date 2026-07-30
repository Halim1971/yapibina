from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Apartment,
    Building,
    Charge,
    ChargeBatch,
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
    PaymentAllocation,
    PaymentMethod,
    User,
)
from app.services import PaymentOverAllocationError
from app.services.charges import create_manual_charge
from app.services.dues_dashboard import get_dues_dashboard
from app.services.payments import (
    auto_allocate_payment,
    get_payment_unallocated_amount,
    record_payment,
)

HOST = "aidat.example.com"
PASSWORD = "SecurePass123"


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def _user(email: str, *, platform: bool = False) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="Test",
        last_name="Kullanıcı",
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
        name=f"{code} Binası",
        code=code,
        is_active=active,
    )
    db.session.add(building)
    db.session.flush()
    return building


def _apartment(
    organization: Organization,
    building: Building,
    unit_code: str,
    *,
    active: bool = True,
) -> Apartment:
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number=unit_code,
        unit_code=unit_code,
        is_active=active,
    )
    db.session.add(apartment)
    db.session.flush()
    return apartment


def _seed_admin(
    *,
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> tuple[Organization, User, Building, Apartment]:
    organization = _organization("aidat", HOST, status=status)
    admin = _user("admin@aidat.example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=admin.id,
            role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    )
    building = _building(organization, "A")
    apartment = _apartment(organization, building, "A-1")
    db.session.commit()
    return organization, admin, building, apartment


def _login(client: FlaskClient, email: str, *, host: str = HOST) -> None:
    response = client.post(
        "/auth/login",
        data={"email": email, "password": PASSWORD},
        headers={"Host": host},
    )
    assert response.status_code == 302


def _batch_data(building: Building, *, year: int = 2026, month: int = 7) -> dict[str, str]:
    return {
        "building_id": str(building.id),
        "period_year": str(year),
        "period_month": str(month),
        "title": "Temmuz 2026 Aidatı",
        "default_amount": "1000.00",
        "due_date": "2026-07-15",
        "description": "",
    }


def _payment_data(amount: str = "1000.00") -> dict[str, str]:
    return {
        "amount": amount,
        "payment_date": "2026-07-10",
        "payment_method": PaymentMethod.BANK_TRANSFER.value,
        "reference": "",
        "description": "",
        "auto_allocate": "y",
    }


def test_dues_access_requires_admin(client: FlaskClient) -> None:
    organization, _, _, _ = _seed_admin()
    response = client.get("/organization/dues", headers={"Host": HOST})
    assert response.status_code == 302

    member = _user("member@aidat.example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
        )
    )
    db.session.commit()
    _login(client, member.email)
    assert client.get("/organization/dues", headers={"Host": HOST}).status_code == 403


def test_admin_sees_only_active_tenant_buildings(client: FlaskClient) -> None:
    organization, admin, building, _ = _seed_admin()
    _building(organization, "PASIF", active=False)
    other = _organization("diger", "diger.example.com")
    foreign = _building(other, "YABANCI")
    db.session.commit()
    _login(client, admin.email)

    response = client.get("/organization/dues", headers={"Host": HOST})
    assert response.status_code == 200
    assert building.name.encode() in response.data
    assert b"PASIF" not in response.data
    assert b"YABANCI" not in response.data

    response = client.get(
        f"/organization/dues?building_id={foreign.id}&year=2026&month=7",
        headers={"Host": HOST},
    )
    assert response.status_code == 404


def test_invalid_period_is_user_friendly(client: FlaskClient) -> None:
    _, admin, building, _ = _seed_admin()
    _login(client, admin.email)
    response = client.get(
        f"/organization/dues?building_id={building.id}&year=1900&month=13",
        headers={"Host": HOST},
    )
    assert response.status_code == 200
    assert "Bina veya dönem seçimi geçerli değil.".encode() in response.data


def test_batch_post_creates_charges_for_active_apartments_and_redirects(
    client: FlaskClient,
) -> None:
    organization, admin, building, _ = _seed_admin()
    _apartment(organization, building, "A-2")
    _apartment(organization, building, "A-3", active=False)
    db.session.commit()
    _login(client, admin.email)

    response = client.post(
        "/organization/dues/batches",
        data=_batch_data(building),
        headers={"Host": HOST},
    )
    assert response.status_code == 302
    assert "building_id=" in response.location
    assert db.session.scalar(select(func.count()).select_from(ChargeBatch)) == 1
    assert db.session.scalar(select(func.count()).select_from(Charge)) == 2


def test_duplicate_period_and_cross_tenant_batch_are_rejected(
    client: FlaskClient,
) -> None:
    _, admin, building, _ = _seed_admin()
    other = _organization("baska", "baska.example.com")
    foreign = _building(other, "B")
    db.session.commit()
    _login(client, admin.email)
    client.post(
        "/organization/dues/batches",
        data=_batch_data(building),
        headers={"Host": HOST},
    )
    duplicate = client.post(
        "/organization/dues/batches",
        data=_batch_data(building),
        headers={"Host": HOST},
        follow_redirects=True,
    )
    assert duplicate.status_code == 200
    assert "Bu bina ve dönem".encode() in duplicate.data
    assert db.session.scalar(select(func.count()).select_from(ChargeBatch)) == 1

    response = client.post(
        "/organization/dues/batches",
        data=_batch_data(foreign),
        headers={"Host": HOST},
    )
    assert response.status_code == 404
    assert db.session.scalar(select(func.count()).select_from(ChargeBatch)) == 1


def test_state_changing_dues_routes_do_not_accept_get(client: FlaskClient) -> None:
    _, admin, building, apartment = _seed_admin()
    _login(client, admin.email)
    assert client.get("/organization/dues/batches", headers={"Host": HOST}).status_code == 405
    assert (
        client.get(
            f"/organization/dues/apartments/{apartment.id}/payments",
            headers={"Host": HOST},
        ).status_code
        == 405
    )
    assert (
        client.get(
            f"/organization/dues/batches/{building.id}/cancel",
            headers={"Host": HOST},
        ).status_code
        == 405
    )


def test_dashboard_uses_only_selected_period_allocations() -> None:
    organization, admin, building, apartment = _seed_admin()
    old_charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title="Haziran",
        description=None,
        amount="400.00",
        due_date=date(2026, 6, 15),
        created_by_user_id=admin.id,
        period_year=2026,
        period_month=6,
    )
    current_charge = create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title="Temmuz",
        description=None,
        amount="1000.00",
        due_date=date(2026, 7, 15),
        created_by_user_id=admin.id,
        period_year=2026,
        period_month=7,
    )
    payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="600.00",
        payment_date=date(2026, 7, 10),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
    )
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    db.session.commit()

    dashboard = get_dues_dashboard(
        db.session,
        organization_id=organization.id,
        building=building,
        year=2026,
        month=7,
    )
    assert old_charge.status is ChargeStatus.POSTED
    assert dashboard.total_charges == Decimal("1000.00")
    assert dashboard.total_collected == Decimal("200.00")
    assert dashboard.total_outstanding == Decimal("800.00")
    assert dashboard.partially_paid_count == 1
    assert current_charge.id is not None


def test_payment_route_auto_allocates_oldest_and_uses_prg(client: FlaskClient) -> None:
    organization, admin, building, apartment = _seed_admin()
    for month in (6, 7):
        create_manual_charge(
            db.session,
            organization_id=organization.id,
            building_id=building.id,
            apartment_id=apartment.id,
            charge_type=ChargeType.MONTHLY_DUE,
            title=f"{month}. ay",
            description=None,
            amount="500.00",
            due_date=date(2026, month, 15),
            created_by_user_id=admin.id,
            period_year=2026,
            period_month=month,
        )
    db.session.commit()
    _login(client, admin.email)

    response = client.post(
        f"/organization/dues/apartments/{apartment.id}/payments",
        data=_payment_data("700.00"),
        headers={"Host": HOST},
    )
    assert response.status_code == 302
    payment = db.session.scalar(select(Payment))
    assert payment is not None
    allocations = db.session.scalars(
        select(PaymentAllocation)
        .where(PaymentAllocation.payment_id == payment.id)
        .order_by(PaymentAllocation.created_at, PaymentAllocation.id)
    ).all()
    assert [allocation.amount for allocation in allocations] == [
        Decimal("500.00"),
        Decimal("200.00"),
    ]
    client.get(response.location, headers={"Host": HOST})
    assert db.session.scalar(select(func.count()).select_from(Payment)) == 1


def test_excess_payment_remains_unallocated(client: FlaskClient) -> None:
    organization, admin, building, apartment = _seed_admin()
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Borç",
        description=None,
        amount="100.00",
        due_date=date.today(),
        created_by_user_id=admin.id,
    )
    db.session.commit()
    _login(client, admin.email)
    client.post(
        f"/organization/dues/apartments/{apartment.id}/payments",
        data=_payment_data("150.00"),
        headers={"Host": HOST},
    )
    payment = db.session.scalar(select(Payment))
    assert payment is not None
    assert get_payment_unallocated_amount(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    ) == Decimal("50.00")


def test_cross_tenant_payment_and_detail_are_not_found(client: FlaskClient) -> None:
    _, admin, _, _ = _seed_admin()
    other = _organization("yabanci", "yabanci.example.com")
    foreign_building = _building(other, "B")
    foreign_apartment = _apartment(other, foreign_building, "B-1")
    db.session.commit()
    _login(client, admin.email)

    detail = client.get(
        f"/organization/dues/apartments/{foreign_apartment.id}",
        headers={"Host": HOST},
    )
    payment = client.post(
        f"/organization/dues/apartments/{foreign_apartment.id}/payments",
        data=_payment_data(),
        headers={"Host": HOST},
    )
    assert detail.status_code == 404
    assert payment.status_code == 404
    assert db.session.scalar(select(func.count()).select_from(Payment)) == 0


def test_apartment_detail_is_user_facing(client: FlaskClient) -> None:
    organization, admin, building, apartment = _seed_admin()
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Temmuz aidatı",
        description=None,
        amount="250.00",
        due_date=date.today(),
        created_by_user_id=admin.id,
    )
    db.session.commit()
    _login(client, admin.email)
    response = client.get(
        f"/organization/dues/apartments/{apartment.id}",
        headers={"Host": HOST},
    )
    assert response.status_code == 200
    assert "Toplam borç".encode() in response.data
    assert "Ödeme gir".encode() in response.data
    for technical_term in (b"PaymentAllocation", b"ChargeBatch", b"Tenant", b"UUID"):
        assert technical_term not in response.data


def _csrf_token(response_data: bytes) -> str:
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response_data)
    assert match is not None
    return match.group(1).decode()


def test_batch_and_payment_require_csrf(
    app: Flask,
    client: FlaskClient,
) -> None:
    _, admin, building, apartment = _seed_admin()
    _login(client, admin.email)
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        client.post(
            "/organization/dues/batches",
            data=_batch_data(building),
            headers={"Host": HOST},
        ).status_code
        == 400
    )
    detail = client.get(
        f"/organization/dues/apartments/{apartment.id}",
        headers={"Host": HOST},
    )
    token = _csrf_token(detail.data)
    payment_data = _payment_data()
    payment_data["csrf_token"] = token
    assert (
        client.post(
            f"/organization/dues/apartments/{apartment.id}/payments",
            data=payment_data,
            headers={"Host": HOST},
        ).status_code
        == 302
    )


def test_payment_and_allocations_roll_back_together(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, admin, _, apartment = _seed_admin()
    _login(client, admin.email)

    def fail_allocation(*args: object, **kwargs: object) -> list[PaymentAllocation]:
        del args, kwargs
        raise PaymentOverAllocationError("Güvenli ödeme hatası.")

    monkeypatch.setattr(
        "app.blueprints.organization.routes.auto_allocate_payment",
        fail_allocation,
    )
    response = client.post(
        f"/organization/dues/apartments/{apartment.id}/payments",
        data=_payment_data(),
        headers={"Host": HOST},
    )
    assert response.status_code == 302
    assert db.session.scalar(select(func.count()).select_from(Payment)) == 0


def test_suspended_organization_and_platform_admin_do_not_gain_access(
    client: FlaskClient,
) -> None:
    organization, _, _, _ = _seed_admin()
    platform = _user("platform@aidat.example.com", platform=True)
    db.session.commit()
    with client.session_transaction(headers={"Host": HOST}) as session:
        session["_user_id"] = str(platform.id)
        session["_fresh"] = True
    assert client.get("/organization/dues", headers={"Host": HOST}).status_code == 403

    organization.status = OrganizationStatus.SUSPENDED
    db.session.commit()
    assert client.get("/organization/dues", headers={"Host": HOST}).status_code == 421


def test_default_period_and_navigation_are_visible(client: FlaskClient) -> None:
    organization, admin, building, first = _seed_admin()
    first.number = "1"
    first.unit_code = "1"
    for number in range(2, 11):
        _apartment(organization, building, str(number))
    db.session.commit()
    _login(client, admin.email)
    response = client.get("/organization/dues", headers={"Host": HOST})
    assert response.status_code == 200
    assert b"Aidatlar" in response.data
    assert b"dues-row" in response.data
    assert b"create-dues" not in response.data
    assert (
        "Tüm aktif bağımsız bölümlere uygula".encode()
        not in response.data
    )
    assert b"\xc3\x96deme gir" not in response.data
    labels = [
        response.data.index(f"<strong>{number}</strong>".encode())
        for number in range(1, 11)
    ]
    assert labels == sorted(labels)


def test_auto_allocation_locking_path_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, admin, building, apartment = _seed_admin()
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Borç",
        description=None,
        amount="100.00",
        due_date=date.today() - timedelta(days=1),
        created_by_user_id=admin.id,
    )
    payment = record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="100.00",
        payment_date=date.today(),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
    )
    from app.services import payments as payment_service

    original = payment_service._lock_payment
    called = False

    def tracked_lock(*args: object, **kwargs: object) -> Payment:
        nonlocal called
        called = True
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(payment_service, "_lock_payment", tracked_lock)
    auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=payment.id,
    )
    assert called
