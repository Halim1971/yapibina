from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask
from sqlalchemy import event

from app.extensions import db
from app.models import (
    Apartment,
    Building,
    Charge,
    ChargeBatchStatus,
    ChargeStatus,
    ChargeType,
    Organization,
    OrganizationStatus,
    Payment,
    PaymentAllocation,
    PaymentMethod,
    PaymentStatus,
    User,
)
from app.services import (
    ChargeHasAllocationsError,
    ChargeOverAllocationError,
    CrossTenantFinancialOperationError,
    DuplicateAllocationError,
    DuplicateChargeBatchError,
    FinancialRecordAlreadyReversedError,
    InvalidAmountError,
    InvalidFinancialStateTransitionError,
    PaymentOverAllocationError,
    ServiceValidationError,
)
from app.services.account_balances import get_apartment_balance
from app.services.charges import (
    cancel_charge_batch,
    create_charge_batch,
    create_manual_charge,
    get_charge_outstanding_amount,
    post_charge_batch,
    reverse_charge,
)
from app.services.payments import (
    allocate_payment,
    auto_allocate_payment,
    get_payment_unallocated_amount,
    record_payment,
    reverse_payment,
)


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def seed_scope(
    slug: str = "finance",
) -> tuple[Organization, Building, Apartment, User]:
    organization = Organization(
        name=slug.title(),
        slug=slug,
        status=OrganizationStatus.ACTIVE,
    )
    user = User(
        email=f"{slug}@example.com",
        password_hash="",
        first_name="Finance",
        last_name="Manager",
    )
    user.set_password("SecurePass123")
    db.session.add_all([organization, user])
    db.session.flush()
    building = Building(
        organization_id=organization.id,
        name="A",
        code="A",
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
    return organization, building, apartment, user


def manual_charge(
    organization: Organization,
    building: Building,
    apartment: Apartment,
    user: User,
    *,
    amount: str = "100.00",
    due_date: date | None = None,
) -> Charge:
    return create_manual_charge(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        charge_type=ChargeType.MANUAL,
        title="Borç",
        description=None,
        amount=amount,
        due_date=due_date or date(2026, 1, 10),
        created_by_user_id=user.id,
    )


def payment(
    organization: Organization,
    building: Building,
    apartment: Apartment,
    user: User,
    *,
    amount: str = "100.00",
) -> Payment:
    return record_payment(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
        amount=amount,
        payment_date=date(2026, 1, 15),
        payment_method=PaymentMethod.BANK_TRANSFER,
        recorded_by_user_id=user.id,
    )


def test_decimal_amounts_are_quantized() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="100.125",
    )
    received = payment(
        organization,
        building,
        apartment,
        user,
        amount="80.126",
    )
    assert charge.original_amount == Decimal("100.13")
    assert received.amount == Decimal("80.13")


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity"])
def test_invalid_charge_amount_is_rejected(amount: str) -> None:
    organization, building, apartment, user = seed_scope()
    with pytest.raises(InvalidAmountError):
        manual_charge(organization, building, apartment, user, amount=amount)


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity"])
def test_invalid_payment_amount_is_rejected(amount: str) -> None:
    organization, building, apartment, user = seed_scope()
    with pytest.raises(InvalidAmountError):
        payment(organization, building, apartment, user, amount=amount)


@pytest.mark.parametrize("month", [0, 13])
def test_invalid_batch_month_is_rejected(month: int) -> None:
    organization, building, _, user = seed_scope()
    with pytest.raises(ServiceValidationError):
        create_charge_batch(
            db.session,
            organization_id=organization.id,
            building_id=building.id,
            period_year=2026,
            period_month=month,
            title="Aidat",
            description=None,
            default_amount="100",
            due_date=date(2026, 1, 10),
            created_by_user_id=user.id,
        )


def test_batch_posts_only_active_apartments_once() -> None:
    organization, building, apartment, user = seed_scope()
    inactive = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="2",
        unit_code="A-2",
        is_active=False,
    )
    active = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="3",
        unit_code="A-3",
    )
    db.session.add_all([inactive, active])
    db.session.flush()
    batch = create_charge_batch(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        period_year=2026,
        period_month=1,
        title="Ocak aidatı",
        description=None,
        default_amount="500",
        due_date=date(2026, 1, 10),
        created_by_user_id=user.id,
    )
    assert batch.status is ChargeBatchStatus.DRAFT
    charges = post_charge_batch(
        db.session,
        organization_id=organization.id,
        batch_id=batch.id,
    )
    assert {item.apartment_id for item in charges} == {apartment.id, active.id}
    assert all(item.original_amount == Decimal("500.00") for item in charges)
    with pytest.raises(InvalidFinancialStateTransitionError):
        post_charge_batch(
            db.session,
            organization_id=organization.id,
            batch_id=batch.id,
        )


def test_batch_posting_rolls_back_all_charges_on_failure() -> None:
    organization, building, _, user = seed_scope()
    db.session.add(
        Apartment(
            organization_id=organization.id,
            building_id=building.id,
            number="2",
            unit_code="A-2",
        )
    )
    db.session.flush()
    batch = create_charge_batch(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        period_year=2026,
        period_month=3,
        title="Mart",
        description=None,
        default_amount="100",
        due_date=date(2026, 3, 10),
        created_by_user_id=user.id,
    )
    insert_count = 0

    def fail_second_insert(*_args: object) -> None:
        nonlocal insert_count
        insert_count += 1
        if insert_count == 2:
            raise RuntimeError("simulated insert failure")

    event.listen(Charge, "before_insert", fail_second_insert)
    try:
        with pytest.raises(RuntimeError, match="simulated"):
            post_charge_batch(
                db.session,
                organization_id=organization.id,
                batch_id=batch.id,
            )
    finally:
        event.remove(Charge, "before_insert", fail_second_insert)
    db.session.refresh(batch)
    assert batch.status is ChargeBatchStatus.DRAFT
    assert (
        db.session.scalar(
            db.select(db.func.count(Charge.id)).where(
                Charge.charge_batch_id == batch.id
            )
        )
        == 0
    )


def test_duplicate_posted_period_is_rejected_but_cancelled_allows_new() -> None:
    organization, building, _, user = seed_scope()
    first = create_charge_batch(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        period_year=2026,
        period_month=2,
        title="Şubat",
        description=None,
        default_amount="100",
        due_date=date(2026, 2, 10),
        created_by_user_id=user.id,
    )
    post_charge_batch(
        db.session,
        organization_id=organization.id,
        batch_id=first.id,
    )
    second = create_charge_batch(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        period_year=2026,
        period_month=2,
        title="Şubat tekrar",
        description=None,
        default_amount="100",
        due_date=date(2026, 2, 10),
        created_by_user_id=user.id,
    )
    with pytest.raises(DuplicateChargeBatchError):
        post_charge_batch(
            db.session,
            organization_id=organization.id,
            batch_id=second.id,
        )
    cancel_charge_batch(
        db.session,
        organization_id=organization.id,
        batch_id=first.id,
        reason="Yeniden oluşturulacak",
    )
    post_charge_batch(
        db.session,
        organization_id=organization.id,
        batch_id=second.id,
    )
    assert first.status is ChargeBatchStatus.CANCELLED
    assert second.status is ChargeBatchStatus.POSTED


def test_batch_and_manual_charge_reject_cross_tenant_scope() -> None:
    first, building, apartment, user = seed_scope("tenant-a")
    second, _, _, second_user = seed_scope("tenant-b")
    with pytest.raises(ServiceValidationError):
        create_charge_batch(
            db.session,
            organization_id=second.id,
            building_id=building.id,
            period_year=2026,
            period_month=1,
            title="Aidat",
            description=None,
            default_amount="100",
            due_date=date(2026, 1, 10),
            created_by_user_id=second_user.id,
        )
    with pytest.raises(CrossTenantFinancialOperationError):
        manual_charge(second, building, apartment, second_user)
    assert first.id != second.id
    assert user.id != second_user.id


def test_posted_charge_is_immutable_and_reversal_is_required() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(organization, building, apartment, user)
    charge.original_amount = Decimal("999.00")
    with pytest.raises(ValueError, match="immutable"):
        db.session.flush()


def test_charge_reversal_rules() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(organization, building, apartment, user)
    reverse_charge(
        db.session,
        organization_id=organization.id,
        charge_id=charge.id,
        reason="Hatalı kayıt",
    )
    assert charge.status is ChargeStatus.REVERSED
    assert (
        get_charge_outstanding_amount(
            db.session,
            organization_id=organization.id,
            charge_id=charge.id,
        )
        == Decimal("0.00")
    )
    with pytest.raises(FinancialRecordAlreadyReversedError):
        reverse_charge(
            db.session,
            organization_id=organization.id,
            charge_id=charge.id,
            reason="Tekrar",
        )


def test_payment_is_immutable_and_reversible() -> None:
    organization, building, apartment, user = seed_scope()
    received = payment(organization, building, apartment, user)
    received.amount = Decimal("999.00")
    with pytest.raises(ValueError, match="immutable"):
        db.session.flush()


def test_allocation_limits_duplicate_and_charge_reversal() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="100",
    )
    received = payment(
        organization,
        building,
        apartment,
        user,
        amount="80",
    )
    allocation = allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
        charge_id=charge.id,
        amount="60",
    )
    assert allocation.amount == Decimal("60.00")
    assert (
        get_payment_unallocated_amount(
            db.session,
            organization_id=organization.id,
            payment_id=received.id,
        )
        == Decimal("20.00")
    )
    assert (
        get_charge_outstanding_amount(
            db.session,
            organization_id=organization.id,
            charge_id=charge.id,
        )
        == Decimal("40.00")
    )
    with pytest.raises(DuplicateAllocationError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=received.id,
            charge_id=charge.id,
            amount="10",
        )
    with pytest.raises(ChargeHasAllocationsError):
        reverse_charge(
            db.session,
            organization_id=organization.id,
            charge_id=charge.id,
            reason="Allocation var",
        )


def test_payment_and_charge_overallocation_are_rejected() -> None:
    organization, building, apartment, user = seed_scope()
    large_charge = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="100",
    )
    small_payment = payment(
        organization,
        building,
        apartment,
        user,
        amount="20",
    )
    with pytest.raises(PaymentOverAllocationError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=small_payment.id,
            charge_id=large_charge.id,
            amount="21",
        )
    small_charge = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="10",
    )
    large_payment = payment(
        organization,
        building,
        apartment,
        user,
        amount="100",
    )
    with pytest.raises(ChargeOverAllocationError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=large_payment.id,
            charge_id=small_charge.id,
            amount="11",
        )


def test_allocation_rejects_other_apartment_and_other_tenant() -> None:
    organization, building, apartment, user = seed_scope()
    other_apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="2",
        unit_code="A-2",
    )
    db.session.add(other_apartment)
    db.session.flush()
    charge = manual_charge(organization, building, apartment, user)
    other_payment = payment(
        organization,
        building,
        other_apartment,
        user,
    )
    with pytest.raises(CrossTenantFinancialOperationError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=other_payment.id,
            charge_id=charge.id,
            amount="10",
        )
    second, second_building, second_apartment, second_user = seed_scope("tenant-two")
    second_payment = payment(
        second,
        second_building,
        second_apartment,
        second_user,
    )
    with pytest.raises(ServiceValidationError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=second_payment.id,
            charge_id=charge.id,
            amount="10",
        )


def test_reversed_records_cannot_be_allocated() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(organization, building, apartment, user)
    received = payment(organization, building, apartment, user)
    reverse_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
        reason="Hatalı",
    )
    with pytest.raises(InvalidFinancialStateTransitionError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=received.id,
            charge_id=charge.id,
            amount="10",
        )
    second_payment = payment(organization, building, apartment, user)
    reverse_charge(
        db.session,
        organization_id=organization.id,
        charge_id=charge.id,
        reason="Hatalı",
    )
    with pytest.raises(InvalidFinancialStateTransitionError):
        allocate_payment(
            db.session,
            organization_id=organization.id,
            payment_id=second_payment.id,
            charge_id=charge.id,
            amount="10",
        )


def test_auto_allocation_is_oldest_first_split_and_apartment_scoped() -> None:
    organization, building, apartment, user = seed_scope()
    oldest = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="40",
        due_date=date(2026, 1, 1),
    )
    newest = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="50",
        due_date=date(2026, 2, 1),
    )
    other_apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number="2",
        unit_code="A-2",
    )
    db.session.add(other_apartment)
    db.session.flush()
    other_charge = manual_charge(
        organization,
        building,
        other_apartment,
        user,
        amount="30",
        due_date=date(2025, 1, 1),
    )
    received = payment(
        organization,
        building,
        apartment,
        user,
        amount="100",
    )
    allocations = auto_allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
    )
    assert [(item.charge_id, item.amount) for item in allocations] == [
        (oldest.id, Decimal("40.00")),
        (newest.id, Decimal("50.00")),
    ]
    assert (
        get_payment_unallocated_amount(
            db.session,
            organization_id=organization.id,
            payment_id=received.id,
        )
        == Decimal("10.00")
    )
    assert other_charge.id not in {item.charge_id for item in allocations}


def test_balance_excludes_reversed_charge_and_payment_allocations() -> None:
    organization, building, apartment, user = seed_scope()
    active_charge = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="100",
    )
    reversed_charge = manual_charge(
        organization,
        building,
        apartment,
        user,
        amount="50",
    )
    reverse_charge(
        db.session,
        organization_id=organization.id,
        charge_id=reversed_charge.id,
        reason="Hatalı",
    )
    received = payment(
        organization,
        building,
        apartment,
        user,
        amount="80",
    )
    allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
        charge_id=active_charge.id,
        amount="60",
    )
    balance = get_apartment_balance(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
    )
    assert balance.total_charges == Decimal("100.00")
    assert balance.total_payments == Decimal("80.00")
    assert balance.total_allocated == Decimal("60.00")
    assert balance.total_outstanding == Decimal("40.00")
    reverse_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
        reason="İade",
    )
    reversed_balance = get_apartment_balance(
        db.session,
        organization_id=organization.id,
        building_id=building.id,
        apartment_id=apartment.id,
    )
    assert reversed_balance.total_payments == Decimal("0.00")
    assert reversed_balance.total_allocated == Decimal("0.00")
    assert reversed_balance.total_outstanding == Decimal("100.00")


def test_payment_reversal_is_idempotency_error_and_allocations_remain() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(organization, building, apartment, user)
    received = payment(organization, building, apartment, user)
    allocation = allocate_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
        charge_id=charge.id,
        amount="100",
    )
    reverse_payment(
        db.session,
        organization_id=organization.id,
        payment_id=received.id,
        reason="İade",
    )
    assert db.session.get(PaymentAllocation, allocation.id) is allocation
    assert received.status is PaymentStatus.REVERSED
    with pytest.raises(FinancialRecordAlreadyReversedError):
        reverse_payment(
            db.session,
            organization_id=organization.id,
            payment_id=received.id,
            reason="Tekrar",
        )


def test_financial_queries_require_tenant_scope() -> None:
    organization, building, apartment, user = seed_scope()
    charge = manual_charge(organization, building, apartment, user)
    received = payment(organization, building, apartment, user)
    foreign_id = uuid.uuid4()
    with pytest.raises(ServiceValidationError):
        get_charge_outstanding_amount(
            db.session,
            organization_id=foreign_id,
            charge_id=charge.id,
        )
    with pytest.raises(ServiceValidationError):
        get_payment_unallocated_amount(
            db.session,
            organization_id=foreign_id,
            payment_id=received.id,
        )


def test_financial_metadata_contains_constraints_and_indexes() -> None:
    tables = db.metadata.tables
    assert {"charge_batches", "charges", "payments", "payment_allocations"} <= set(
        tables
    )
    allocation_uniques = {
        constraint.name
        for constraint in tables["payment_allocations"].constraints
        if constraint.name
    }
    assert "uq_payment_allocations_payment_charge" in allocation_uniques
    batch_indexes = {index.name for index in tables["charge_batches"].indexes}
    assert "uq_charge_batches_posted_period" in batch_indexes
