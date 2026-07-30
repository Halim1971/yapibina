from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import event

from app.extensions import db
from app.imports.models import ImportRun, ImportRunStatus
from app.models import (
    Apartment,
    ApartmentMembership,
    ApartmentMembershipRole,
    Building,
    BuildingBankTransaction,
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
from app.services.organization_dashboard import get_organization_dashboard
from app.services.payments import auto_allocate_payment, record_payment

HOST = "dashboard.example.com"
PASSWORD = "SecurePass123"
JULY = date(2026, 7, 20)


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def _user(email: str) -> User:
    user = User(
        email=email,
        password_hash="",
        first_name="Dashboard",
        last_name="Kullanıcı",
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


def _seed_scope() -> tuple[Organization, User, Building, Apartment]:
    organization = _organization("dashboard", HOST)
    admin = _user("dashboard-admin@example.com")
    resident = _user("dashboard-resident@example.com")
    db.session.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=admin.id,
                role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=resident.id,
                role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            ),
        ]
    )
    building = Building(
        organization_id=organization.id,
        name="Merkez Apartmanı",
        code="MERKEZ",
    )
    db.session.add(building)
    db.session.flush()
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="1",
        unit_code="A-1",
    )
    db.session.add(apartment)
    db.session.flush()
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.RESIDENT,
        )
    )
    db.session.commit()
    return organization, admin, building, apartment


def _login(client: FlaskClient, email: str) -> None:
    response = client.post(
        "/auth/login",
        data={"email": email, "password": PASSWORD},
        headers={"Host": HOST},
    )
    assert response.status_code == 302


def _add_finances(
    organization: Organization,
    admin: User,
    building: Building,
    apartment: Apartment,
) -> None:
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Haziran borcu",
        description=None,
        amount="50.00",
        due_date=date(2026, 6, 15),
        created_by_user_id=admin.id,
    )
    create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MONTHLY_DUE,
        title="Temmuz aidatı",
        description=None,
        amount="100.00",
        due_date=date(2026, 7, 15),
        created_by_user_id=admin.id,
    )
    old_payment = record_payment(
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
        payment_id=old_payment.id,
    )
    record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount="500.00",
        payment_date=date(2026, 7, 10),
        payment_method=PaymentMethod.CASH,
        recorded_by_user_id=admin.id,
        description="Dağıtılmamış ödeme",
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
    db.session.commit()


def test_dashboard_access_and_empty_state(client: FlaskClient) -> None:
    organization = _organization("dashboard", HOST)
    admin = _user("dashboard-admin@example.com")
    member = _user("dashboard-member@example.com")
    db.session.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=admin.id,
                role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=member.id,
                role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
            ),
        ]
    )
    db.session.commit()
    _login(client, admin.email)
    response = client.get("/organization/dashboard", headers={"Host": HOST})
    assert response.status_code == 200
    assert "Genel Bakış".encode() in response.data
    assert b"Binalar" in response.data
    assert b"Banka Hareketleri" in response.data
    assert b"Aidatlar" in response.data
    assert b"Veri \xc4\xb0\xc3\xa7e Aktarma" not in response.data
    assert b"Toplam bina" not in response.data
    assert b"Son finansal hareketler" not in response.data

    csrf_match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert csrf_match is not None
    logout = client.post(
        "/auth/logout",
        data={"csrf_token": csrf_match.group(1).decode()},
        headers={"Host": HOST},
    )
    assert logout.status_code == 302
    assert logout.headers["Location"].endswith("/auth/login")
    _login(client, member.email)
    assert (
        client.get("/organization/dashboard", headers={"Host": HOST}).status_code
        == 403
    )
    assert organization.id is not None


def test_organization_bank_movements_are_building_and_tenant_scoped(
    client: FlaskClient,
) -> None:
    organization = _organization("bank-dashboard", HOST)
    admin = _user("bank-dashboard-admin@example.com")
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=admin.id,
            role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    )
    first = Building(
        organization_id=organization.id,
        name="Birinci Apartman",
        code="BANK-1",
    )
    second = Building(
        organization_id=organization.id,
        name="İkinci Apartman",
        code="BANK-2",
    )
    other = _organization("other-bank", "other-bank.example.com")
    other_building = Building(
        organization_id=other.id,
        name="Başka Tenant Binası",
        code="OTHER-BANK",
    )
    db.session.add_all([first, second, other_building])
    db.session.flush()
    for building, source_key, description in (
        (first, "BANK-1-TX", "Birinci bina hareketi"),
        (second, "BANK-2-TX", "İkinci bina hareketi"),
        (other_building, "OTHER-TX", "Başka tenant hareketi"),
    ):
        db.session.add(
            BuildingBankTransaction(
                organization_id=building.organization_id,
                building_id=building.id,
                source_key=source_key,
                transaction_date=date(2026, 7, 1),
                description=description,
                transaction_type="credit",
                inflow=Decimal("100.00"),
                outflow=Decimal("0.00"),
                balance=Decimal("100.00"),
                category="Aidat",
                reference=source_key,
            )
        )
    db.session.commit()

    _login(client, admin.email)
    response = client.get(
        f"/organization/bank-transactions?building_id={second.id}",
        headers={"Host": HOST},
    )

    assert response.status_code == 200
    assert "İkinci bina hareketi".encode() in response.data
    assert b"Birinci bina hareketi" not in response.data
    assert "Başka tenant hareketi".encode() not in response.data
    assert (
        client.get(
            f"/organization/bank-transactions?building_id={other_building.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )


def test_dashboard_metrics_imports_movements_and_tenant_isolation() -> None:
    organization, admin, building, apartment = _seed_scope()
    _add_finances(organization, admin, building, apartment)
    other = _organization("other-dashboard", "other-dashboard.example.com")
    other_building = Building(
        organization_id=other.id,
        name="Gizli Bina",
        code="GIZLI",
    )
    db.session.add(other_building)
    db.session.flush()
    other_apartment = Apartment(
        organization_id=other.id,
        building_id=other_building.id,
        number="9",
        unit_code="X-9",
    )
    db.session.add(other_apartment)
    db.session.flush()
    create_manual_charge(
        db.session,
        organization_id=other.id,
        building_id=other_building.id,
        apartment_id=other_apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Gizli borç",
        description=None,
        amount="9999.00",
        due_date=date(2026, 7, 1),
        created_by_user_id=admin.id,
    )
    successful = ImportRun(
        organization_id=organization.id,
        source_system="standard_excel",
        dataset_name="Demo",
        dataset_version="1",
        schema_version="1",
        manifest_sha256="0" * 64,
        package_fingerprint="1" * 64,
        status=ImportRunStatus.COMPLETED,
        started_at=datetime(2026, 7, 18, 10, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 18, 11, tzinfo=timezone.utc),
        inserted_count=5,
        updated_count=2,
        skipped_count=3,
        expense_count=4,
        announcement_count=6,
    )
    failed = ImportRun(
        organization_id=organization.id,
        source_system="standard_excel",
        dataset_name="Hatalı",
        dataset_version="2",
        schema_version="1",
        manifest_sha256="2" * 64,
        package_fingerprint="3" * 64,
        status=ImportRunStatus.FAILED,
        started_at=datetime(2026, 7, 19, 10, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 19, 11, tzinfo=timezone.utc),
        error_count=1,
        error_summary="Doğrulama başarısız",
    )
    db.session.add_all([successful, failed])
    db.session.commit()

    dashboard = get_organization_dashboard(
        db.session,
        organization_id=organization.id,
        timezone_name="Europe/Istanbul",
        reference_date=JULY,
    )
    assert dashboard.building_count == 1
    assert dashboard.apartment_count == 1
    assert dashboard.active_resident_count == 1
    assert dashboard.outstanding_debt == Decimal("110.00")
    assert dashboard.current_month_charges == Decimal("100.00")
    assert dashboard.current_month_payments == Decimal("540.00")
    assert dashboard.collection_rate == Decimal("540.00")
    assert isinstance(dashboard.outstanding_debt, Decimal)
    assert dashboard.latest_import_failed
    assert dashboard.successful_import is not None
    assert dashboard.successful_import.inserted == 5
    assert dashboard.successful_import.deferred == 10
    assert len(dashboard.buildings) == 1
    assert dashboard.buildings[0].outstanding_debt == Decimal("110.00")
    assert len(dashboard.movements) == 5
    assert dashboard.movements[0].movement_date >= dashboard.movements[-1].movement_date
    assert all(item.building_name != "Gizli Bina" for item in dashboard.movements)
    assert all(item.amount != Decimal("9999.00") for item in dashboard.movements)


def test_zero_accrual_ratio_and_query_count_regression(app: Flask) -> None:
    organization, _, _, _ = _seed_scope()
    statements = 0

    def count_statement(*args: object, **kwargs: object) -> None:
        nonlocal statements
        del args, kwargs
        statements += 1

    event.listen(
        db.engine,
        "before_cursor_execute",
        count_statement,
    )
    try:
        dashboard = get_organization_dashboard(
            db.session,
            organization_id=organization.id,
            timezone_name="Europe/Istanbul",
            reference_date=JULY,
        )
    finally:
        event.remove(
            db.engine,
            "before_cursor_execute",
            count_statement,
        )
    assert dashboard.current_month_charges == Decimal("0.00")
    assert dashboard.collection_rate is None
    assert statements <= 13
    assert app is not None
