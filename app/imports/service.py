from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash

from app.imports.constants import (
    ENTITY_ANNOUNCEMENT,
    ENTITY_BANK_TRANSACTION,
    ENTITY_CHARGE,
    ENTITY_EXPENSE,
    ENTITY_PAYMENT,
    ENTITY_RESIDENT,
    ENTITY_SITE,
    ENTITY_UNIT,
    MAPPED_ENTITY_TYPES,
)
from app.imports.exceptions import (
    ConcurrentImportError,
    CriticalFinancialChangeError,
    ImportConflictError,
    ImporterError,
)
from app.imports.models import ExternalRecordMap, ImportRun, ImportRunStatus
from app.imports.reader import validate_package_relationships
from app.imports.schemas import (
    BankTransactionRow,
    ChargeRow,
    DemoAnnouncementRow,
    ExpenseRow,
    ImportResult,
    PaymentRow,
    ResidentUnitRow,
    SiteRow,
    StandardPackage,
)
from app.models import (
    Announcement,
    AnnouncementAudienceScope,
    AnnouncementBuilding,
    AnnouncementStatus,
    Apartment,
    ApartmentExpenseContribution,
    ApartmentMembership,
    ApartmentMembershipRole,
    Building,
    BuildingBankTransaction,
    BuildingExpense,
    Charge,
    ChargeStatus,
    ChargeType,
    Organization,
    OrganizationMembership,
    OrganizationMembershipRole,
    Payment,
    PaymentMethod,
    User,
    UserStatus,
)
from app.models.base import utc_now
from app.services import EntityNotFoundError, ServiceValidationError, SessionLike
from app.services.payments import allocate_payment, auto_allocate_payment, record_payment

MappedEntity = TypeVar(
    "MappedEntity",
    Building,
    Apartment,
    User,
    Charge,
    Payment,
    BuildingExpense,
    BuildingBankTransaction,
    Announcement,
)


class _Counters:
    def __init__(self) -> None:
        self.inserted = 0
        self.updated = 0
        self.skipped = 0


def _hash_values(**values: object) -> str:
    encoded = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mapping(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    source_system: str,
    entity_type: str,
    source_key: str,
) -> ExternalRecordMap | None:
    if entity_type not in MAPPED_ENTITY_TYPES:
        raise ImportConflictError("Desteklenmeyen external entity type.")
    return session.scalar(
        select(ExternalRecordMap).where(
            ExternalRecordMap.organization_id == organization_id,
            ExternalRecordMap.source_system == source_system,
            ExternalRecordMap.entity_type == entity_type,
            ExternalRecordMap.source_key == source_key,
        )
    )


def _map_record(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    entity_type: str,
    source_key: str,
    internal_id: uuid.UUID,
    payload_hash: str,
) -> ExternalRecordMap:
    mapping = ExternalRecordMap(
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=entity_type,
        source_key=source_key,
        internal_id=internal_id,
        import_run_id=run.id,
        source_payload_hash=payload_hash,
    )
    session.add(mapping)
    session.flush()
    return mapping


def _touch_mapping(
    mapping: ExternalRecordMap,
    *,
    run: ImportRun,
    payload_hash: str,
) -> None:
    mapping.last_seen_at = utc_now()
    mapping.import_run_id = run.id
    mapping.source_payload_hash = payload_hash


def _mapped_entity(
    session: SessionLike,
    model: type[MappedEntity],
    mapping: ExternalRecordMap,
    organization_id: uuid.UUID,
) -> MappedEntity:
    entity = session.get(model, mapping.internal_id)
    if entity is None:
        raise ImportConflictError("External mapping iç kaydı bulunamadı.")
    entity_organization = getattr(entity, "organization_id", organization_id)
    if entity_organization != organization_id:
        raise ImportConflictError("External mapping tenant sınırını ihlal ediyor.")
    return entity


def _import_site(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: SiteRow,
    counters: _Counters,
) -> Building:
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_SITE,
        source_key=row.source_site_key,
    )
    if mapping is None:
        building = Building(
            organization_id=run.organization_id,
            name=row.site_name,
            code=row.source_site_key,
            address_line=row.address_line,
            district=row.district,
            city=row.city,
            is_active=row.is_active,
        )
        session.add(building)
        session.flush()
        _map_record(
            session,
            run=run,
            source_system=source_system,
            entity_type=ENTITY_SITE,
            source_key=row.source_site_key,
            internal_id=building.id,
            payload_hash=row.payload_hash,
        )
        counters.inserted += 1
        return building
    building = _mapped_entity(session, Building, mapping, run.organization_id)
    assert isinstance(building, Building)
    if mapping.source_payload_hash == row.payload_hash:
        _touch_mapping(mapping, run=run, payload_hash=row.payload_hash)
        counters.skipped += 1
        return building
    building.name = row.site_name
    building.address_line = row.address_line
    building.district = row.district
    building.city = row.city
    building.is_active = row.is_active
    _touch_mapping(mapping, run=run, payload_hash=row.payload_hash)
    counters.updated += 1
    return building


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else "Resident"


def _ensure_organization_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user: User,
) -> None:
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if membership is None:
        session.add(
            OrganizationMembership(
                organization_id=organization_id,
                user_id=user.id,
                role=OrganizationMembershipRole.ORGANIZATION_MEMBER,
                is_active=True,
            )
        )
    elif membership.role is OrganizationMembershipRole.ORGANIZATION_MEMBER:
        membership.is_active = True


def _import_resident(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: ResidentUnitRow,
    counters: _Counters,
) -> User:
    payload_hash = _hash_values(
        resident_full_name=row.resident_full_name,
        phone=row.phone,
        email=row.email,
        is_active=row.is_active,
    )
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_RESIDENT,
        source_key=row.resident_source_key,
    )
    first_name, last_name = _split_name(row.resident_full_name)
    if mapping is None:
        user = session.scalar(select(User).where(User.email == row.email))
        if user is None:
            user = User(
                email=row.email,
                password_hash=generate_password_hash(
                    row.initial_password or secrets.token_urlsafe(32)
                ),
                first_name=first_name,
                last_name=last_name,
                phone=row.phone,
                status=UserStatus.ACTIVE if row.is_active else UserStatus.INACTIVE,
            )
            session.add(user)
            session.flush()
        _ensure_organization_membership(
            session,
            organization_id=run.organization_id,
            user=user,
        )
        _map_record(
            session,
            run=run,
            source_system=source_system,
            entity_type=ENTITY_RESIDENT,
            source_key=row.resident_source_key,
            internal_id=user.id,
            payload_hash=payload_hash,
        )
        counters.inserted += 1
        return user
    user = _mapped_entity(session, User, mapping, run.organization_id)
    assert isinstance(user, User)
    if user.email != row.email:
        raise ImportConflictError("Resident e-posta değişikliği otomatik uygulanamaz.")
    _ensure_organization_membership(
        session,
        organization_id=run.organization_id,
        user=user,
    )
    if mapping.source_payload_hash == payload_hash:
        _touch_mapping(mapping, run=run, payload_hash=payload_hash)
        counters.skipped += 1
        return user
    user.first_name = first_name
    user.last_name = last_name
    user.phone = row.phone
    _touch_mapping(mapping, run=run, payload_hash=payload_hash)
    counters.updated += 1
    return user


def _ensure_apartment_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment: Apartment,
    user: User,
) -> None:
    membership = session.scalar(
        select(ApartmentMembership).where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.apartment_id == apartment.id,
            ApartmentMembership.user_id == user.id,
            ApartmentMembership.is_active.is_(True),
        )
    )
    if membership is None:
        session.add(
            ApartmentMembership(
                organization_id=organization_id,
                apartment_id=apartment.id,
                user_id=user.id,
                role=ApartmentMembershipRole.RESIDENT,
                is_active=True,
            )
        )


def _import_unit(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: ResidentUnitRow,
    building: Building,
    resident: User,
    counters: _Counters,
) -> Apartment:
    payload_hash = _hash_values(
        source_site_key=row.source_site_key,
        block_name=row.block_name,
        unit_number=row.unit_number,
        floor_label=row.floor_label,
        is_active=row.is_active,
    )
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_UNIT,
        source_key=row.source_unit_key,
    )
    unit_code = (
        f"{row.block_name}-{row.unit_number}"
        if row.block_name
        else row.unit_number
    )
    if mapping is None:
        apartment = Apartment(
            organization_id=run.organization_id,
            building_id=building.id,
            number=row.unit_number,
            floor=row.floor_label,
            block=row.block_name,
            unit_code=unit_code,
            is_active=row.is_active,
        )
        session.add(apartment)
        session.flush()
        _map_record(
            session,
            run=run,
            source_system=source_system,
            entity_type=ENTITY_UNIT,
            source_key=row.source_unit_key,
            internal_id=apartment.id,
            payload_hash=payload_hash,
        )
        counters.inserted += 1
    else:
        apartment = _mapped_entity(session, Apartment, mapping, run.organization_id)
        assert isinstance(apartment, Apartment)
        if apartment.building_id != building.id:
            raise ImportConflictError("Unit site değişikliği otomatik uygulanamaz.")
        if mapping.source_payload_hash == payload_hash:
            _touch_mapping(mapping, run=run, payload_hash=payload_hash)
            counters.skipped += 1
        else:
            apartment.number = row.unit_number
            apartment.floor = row.floor_label
            apartment.block = row.block_name
            apartment.unit_code = unit_code
            apartment.is_active = row.is_active
            _touch_mapping(mapping, run=run, payload_hash=payload_hash)
            counters.updated += 1
    _ensure_apartment_membership(
        session,
        organization_id=run.organization_id,
        apartment=apartment,
        user=resident,
    )
    return apartment


def _import_charge(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: ChargeRow,
    apartment: Apartment,
    actor: User,
    counters: _Counters,
) -> Charge:
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_CHARGE,
        source_key=row.source_charge_key,
    )
    charge_type = ChargeType(row.charge_type)
    if mapping is None:
        charge = Charge(
            organization_id=run.organization_id,
            building_id=apartment.building_id,
            apartment_id=apartment.id,
            charge_batch_id=None,
            charge_type=charge_type,
            title=row.title,
            description=row.description,
            period_year=row.period_year,
            period_month=row.period_month,
            original_amount=row.amount,
            due_date=row.due_date,
            status=ChargeStatus.POSTED,
            created_by_user_id=actor.id,
        )
        session.add(charge)
        session.flush()
        _map_record(
            session,
            run=run,
            source_system=source_system,
            entity_type=ENTITY_CHARGE,
            source_key=row.source_charge_key,
            internal_id=charge.id,
            payload_hash=row.payload_hash,
        )
        counters.inserted += 1
        return charge
    charge = _mapped_entity(session, Charge, mapping, run.organization_id)
    assert isinstance(charge, Charge)
    if mapping.source_payload_hash == row.payload_hash:
        _touch_mapping(mapping, run=run, payload_hash=row.payload_hash)
        counters.skipped += 1
        return charge
    if (
        charge.apartment_id != apartment.id
        or charge.building_id != apartment.building_id
        or charge.original_amount != row.amount
        or charge.due_date != row.due_date
        or charge.charge_type is not charge_type
        or charge.period_year != row.period_year
        or charge.period_month != row.period_month
    ):
        raise CriticalFinancialChangeError(
            f"Charge kritik alan değişikliği reddedildi: {row.source_charge_key}"
        )
    charge.title = row.title
    charge.description = row.description
    _touch_mapping(mapping, run=run, payload_hash=row.payload_hash)
    counters.updated += 1
    return charge


def _import_payment(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: PaymentRow,
    apartment: Apartment,
    resident: User,
    actor: User,
    counters: _Counters,
) -> Payment:
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_PAYMENT,
        source_key=row.source_payment_key,
    )
    payment_method = PaymentMethod(row.payment_method)
    if mapping is None:
        payment = record_payment(
            session,
            organization_id=run.organization_id,
            building_id=apartment.building_id,
            apartment_id=apartment.id,
            payer_user_id=resident.id,
            amount=row.amount,
            payment_date=row.payment_date,
            payment_method=payment_method,
            recorded_by_user_id=actor.id,
            reference=row.reference,
            description=row.description,
        )
        if row.target_charge_source_key:
            charge_mapping = _mapping(
                session,
                organization_id=run.organization_id,
                source_system=source_system,
                entity_type=ENTITY_CHARGE,
                source_key=row.target_charge_source_key,
            )
            if charge_mapping is None:
                raise ImportConflictError("Ödemenin aidat kaydı bulunamadı.")
            charge = _mapped_entity(
                session, Charge, charge_mapping, run.organization_id
            )
            allocate_payment(
                session,
                organization_id=run.organization_id,
                payment_id=payment.id,
                charge_id=charge.id,
                amount=row.amount,
            )
        else:
            auto_allocate_payment(
                session,
                organization_id=run.organization_id,
                payment_id=payment.id,
            )
        _map_record(
            session,
            run=run,
            source_system=source_system,
            entity_type=ENTITY_PAYMENT,
            source_key=row.source_payment_key,
            internal_id=payment.id,
            payload_hash=row.payload_hash,
        )
        counters.inserted += 1
        return payment
    payment = _mapped_entity(session, Payment, mapping, run.organization_id)
    assert isinstance(payment, Payment)
    if mapping.source_payload_hash == row.payload_hash:
        _touch_mapping(mapping, run=run, payload_hash=row.payload_hash)
        counters.skipped += 1
        return payment
    if (
        payment.apartment_id != apartment.id
        or payment.building_id != apartment.building_id
        or payment.amount != row.amount
        or payment.payment_date != row.payment_date
        or payment.payment_method is not payment_method
    ):
        raise CriticalFinancialChangeError(
            f"Payment kritik alan değişikliği reddedildi: {row.source_payment_key}"
        )
    payment.reference = row.reference
    payment.description = row.description
    _touch_mapping(mapping, run=run, payload_hash=row.payload_hash)
    counters.updated += 1
    return payment


def _system_actor(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
) -> User:
    if created_by_user_id is not None:
        user = session.get(User, created_by_user_id)
        if user is None:
            raise EntityNotFoundError("Importer actor kullanıcısı bulunamadı.")
        return user
    email = f"importer-{organization_id}@yapibina.local"
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            first_name="Yapıbina",
            last_name="Importer",
            status=UserStatus.INACTIVE,
        )
        session.add(user)
        session.flush()
    return user


def _import_expense(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: ExpenseRow,
    building: Building,
    apartments: dict[str, Apartment],
    counters: _Counters,
) -> None:
    source_key = str(row.source_expense_key)
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_EXPENSE,
        source_key=source_key,
    )
    payload_hash = str(row.payload_hash)
    if mapping is not None:
        expense = _mapped_entity(session, BuildingExpense, mapping, run.organization_id)
        if mapping.source_payload_hash != payload_hash:
            raise ImportConflictError(f"Gider kritik değişikliği reddedildi: {source_key}")
        _touch_mapping(mapping, run=run, payload_hash=payload_hash)
        counters.skipped += 1
        return
    expense = BuildingExpense(
        organization_id=run.organization_id,
        building_id=building.id,
        source_key=source_key,
        expense_date=row.expense_date,
        expense_month=row.expense_month,
        category=row.category,
        description=row.description,
        payment_method=row.payment_method,
        amount=row.amount,
    )
    session.add(expense)
    session.flush()
    for unit_key, amount in row.contributions:
        session.add(
            ApartmentExpenseContribution(
                organization_id=run.organization_id,
                expense_id=expense.id,
                apartment_id=apartments[unit_key].id,
                amount=amount,
            )
        )
    _map_record(
        session,
        run=run,
        source_system=source_system,
        entity_type=ENTITY_EXPENSE,
        source_key=source_key,
        internal_id=expense.id,
        payload_hash=payload_hash,
    )
    counters.inserted += 1


def _import_bank_transaction(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: BankTransactionRow,
    building: Building,
    counters: _Counters,
) -> None:
    source_key = str(row.source_transaction_key)
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_BANK_TRANSACTION,
        source_key=source_key,
    )
    payload_hash = str(row.payload_hash)
    if mapping is not None:
        _mapped_entity(session, BuildingBankTransaction, mapping, run.organization_id)
        if mapping.source_payload_hash != payload_hash:
            raise ImportConflictError(
                f"Banka hareketi kritik değişikliği reddedildi: {source_key}"
            )
        _touch_mapping(mapping, run=run, payload_hash=payload_hash)
        counters.skipped += 1
        return
    movement = BuildingBankTransaction(
        organization_id=run.organization_id,
        building_id=building.id,
        source_key=source_key,
        transaction_date=row.transaction_date,
        description=row.description,
        transaction_type=row.transaction_type,
        inflow=row.inflow,
        outflow=row.outflow,
        balance=row.balance,
        category=row.category,
        reference=row.reference,
    )
    session.add(movement)
    session.flush()
    _map_record(
        session,
        run=run,
        source_system=source_system,
        entity_type=ENTITY_BANK_TRANSACTION,
        source_key=source_key,
        internal_id=movement.id,
        payload_hash=payload_hash,
    )
    counters.inserted += 1


def _import_demo_announcement(
    session: SessionLike,
    *,
    run: ImportRun,
    source_system: str,
    row: DemoAnnouncementRow,
    building: Building,
    actor: User,
    counters: _Counters,
) -> None:
    source_key = str(row.source_announcement_key)
    mapping = _mapping(
        session,
        organization_id=run.organization_id,
        source_system=source_system,
        entity_type=ENTITY_ANNOUNCEMENT,
        source_key=source_key,
    )
    payload_hash = str(row.payload_hash)
    if mapping is not None:
        _mapped_entity(session, Announcement, mapping, run.organization_id)
        if mapping.source_payload_hash != payload_hash:
            raise ImportConflictError(f"Duyuru değişikliği reddedildi: {source_key}")
        _touch_mapping(mapping, run=run, payload_hash=payload_hash)
        counters.skipped += 1
        return
    announcement = Announcement(
        organization_id=run.organization_id,
        created_by_user_id=actor.id,
        title=row.title,
        body=row.body,
        status=AnnouncementStatus.PUBLISHED,
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        published_at=row.published_at,
    )
    session.add(announcement)
    session.flush()
    session.add(
        AnnouncementBuilding(
            organization_id=run.organization_id,
            announcement_id=announcement.id,
            building_id=building.id,
        )
    )
    _map_record(
        session,
        run=run,
        source_system=source_system,
        entity_type=ENTITY_ANNOUNCEMENT,
        source_key=source_key,
        internal_id=announcement.id,
        payload_hash=payload_hash,
    )
    counters.inserted += 1


def _apply_package(
    session: SessionLike,
    *,
    run: ImportRun,
    package: StandardPackage,
    source_system: str,
    created_by_user_id: uuid.UUID | None,
) -> _Counters:
    validate_package_relationships(package)
    actor = _system_actor(
        session,
        organization_id=run.organization_id,
        created_by_user_id=created_by_user_id,
    )
    counters = _Counters()
    buildings = {
        row.source_site_key: _import_site(
            session,
            run=run,
            source_system=source_system,
            row=row,
            counters=counters,
        )
        for row in package.sites
    }
    apartments: dict[str, Apartment] = {}
    residents: dict[str, User] = {}
    for unit_row in package.units:
        resident = _import_resident(
            session,
            run=run,
            source_system=source_system,
            row=unit_row,
            counters=counters,
        )
        apartment = _import_unit(
            session,
            run=run,
            source_system=source_system,
            row=unit_row,
            building=buildings[unit_row.source_site_key],
            resident=resident,
            counters=counters,
        )
        residents[unit_row.source_unit_key] = resident
        apartments[unit_row.source_unit_key] = apartment
    for charge_row in sorted(
        package.charges,
        key=lambda item: (
            item.due_date,
            item.source_site_key,
            item.source_unit_key,
            item.source_charge_key,
        ),
    ):
        _import_charge(
            session,
            run=run,
            source_system=source_system,
            row=charge_row,
            apartment=apartments[charge_row.source_unit_key],
            actor=actor,
            counters=counters,
        )
    for payment_row in sorted(
        package.payments,
        key=lambda item: (
            item.payment_date,
            item.source_site_key,
            item.source_unit_key,
            item.source_payment_key,
        ),
    ):
        _import_payment(
            session,
            run=run,
            source_system=source_system,
            row=payment_row,
            apartment=apartments[payment_row.source_unit_key],
            resident=residents[payment_row.source_unit_key],
            actor=actor,
            counters=counters,
        )
    for expense_row in package.expenses:
        _import_expense(
            session,
            run=run,
            source_system=source_system,
            row=expense_row,
            building=buildings[expense_row.source_site_key],
            apartments=apartments,
            counters=counters,
        )
    for transaction_row in package.bank_transactions:
        _import_bank_transaction(
            session,
            run=run,
            source_system=source_system,
            row=transaction_row,
            building=buildings[transaction_row.source_site_key],
            counters=counters,
        )
    for announcement_row in package.demo_announcements:
        _import_demo_announcement(
            session,
            run=run,
            source_system=source_system,
            row=announcement_row,
            building=buildings[announcement_row.source_site_key],
            actor=actor,
            counters=counters,
        )
    session.flush()
    return counters


def _new_run(
    package: StandardPackage,
    *,
    organization_id: uuid.UUID,
    source_system: str,
    created_by_user_id: uuid.UUID | None,
) -> ImportRun:
    return ImportRun(
        organization_id=organization_id,
        source_system=source_system,
        dataset_name=package.dataset_name,
        dataset_version=package.dataset_version,
        schema_version=package.schema_version,
        manifest_sha256=package.manifest_sha256,
        package_fingerprint=package.fingerprint,
        status=ImportRunStatus.RUNNING,
        started_at=utc_now(),
        created_by_user_id=created_by_user_id,
        site_count=len(package.sites),
        unit_count=len(package.units),
        resident_count=len(package.units),
        charge_count=len(package.charges),
        payment_count=len(package.payments),
        expense_count=package.expense_count,
        announcement_count=package.announcement_count,
    )


def _existing_completed_run(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    source_system: str,
    fingerprint: str,
) -> ImportRun | None:
    return session.scalar(
        select(ImportRun).where(
            ImportRun.organization_id == organization_id,
            ImportRun.source_system == source_system,
            ImportRun.package_fingerprint == fingerprint,
            ImportRun.status == ImportRunStatus.COMPLETED,
        )
    )


def import_standard_package(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    package: StandardPackage,
    source_system: str,
    created_by_user_id: uuid.UUID | None = None,
    dry_run: bool = False,
) -> ImportResult:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise EntityNotFoundError("Hedef organization bulunamadı.")
    completed = _existing_completed_run(
        session,
        organization_id=organization_id,
        source_system=source_system,
        fingerprint=package.fingerprint,
    )
    deferred = (
        0
        if package.expenses or package.demo_announcements
        else package.expense_count + package.announcement_count
    )
    if completed is not None:
        return ImportResult(
            run_id=str(completed.id),
            status="already_imported",
            fingerprint=package.fingerprint,
            inserted=0,
            updated=0,
            skipped=(
                len(package.sites)
                + len(package.units) * 2
                + len(package.charges)
                + len(package.payments)
                + len(package.expenses)
                + len(package.bank_transactions)
                + len(package.demo_announcements)
            ),
            deferred=deferred,
        )
    if dry_run:
        transaction = session.begin_nested()
        try:
            run = _new_run(
                package,
                organization_id=organization_id,
                source_system=source_system,
                created_by_user_id=created_by_user_id,
            )
            session.add(run)
            session.flush()
            counters = _apply_package(
                session,
                run=run,
                package=package,
                source_system=source_system,
                created_by_user_id=created_by_user_id,
            )
        finally:
            transaction.rollback()
            session.expire_all()
        return ImportResult(
            run_id=None,
            status="dry_run",
            fingerprint=package.fingerprint,
            inserted=counters.inserted,
            updated=counters.updated,
            skipped=counters.skipped,
            deferred=deferred,
        )

    run = _new_run(
        package,
        organization_id=organization_id,
        source_system=source_system,
        created_by_user_id=created_by_user_id,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ConcurrentImportError(
            "Bu organization için başka bir import çalışıyor."
        ) from error

    try:
        locked_organization = session.scalar(
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update()
        )
        if locked_organization is None:
            raise EntityNotFoundError("Hedef organization bulunamadı.")
        loaded_run = session.get(ImportRun, run.id)
        assert loaded_run is not None
        run = loaded_run
        counters = _apply_package(
            session,
            run=run,
            package=package,
            source_system=source_system,
            created_by_user_id=created_by_user_id,
        )
        run.inserted_count = counters.inserted
        run.updated_count = counters.updated
        run.skipped_count = counters.skipped
        run.status = ImportRunStatus.COMPLETED
        run.finished_at = utc_now()
        run.import_metadata = {
            "deferred_count": deferred,
            "deferred_entities": ["expense", "announcement"],
            "deletion_policy": "no_delete",
        }
        session.commit()
    except (ImporterError, ServiceValidationError, SQLAlchemyError, ValueError) as error:
        session.rollback()
        failed_run = session.get(ImportRun, run.id)
        if failed_run is not None:
            failed_run.status = ImportRunStatus.FAILED
            failed_run.finished_at = utc_now()
            failed_run.error_count = 1
            failed_run.error_summary = str(error)[:2000]
            session.commit()
        if isinstance(error, ImporterError):
            raise
        raise ImportConflictError("Import işlemi güvenli biçimde geri alındı.") from error
    return ImportResult(
        run_id=str(run.id),
        status="completed",
        fingerprint=package.fingerprint,
        inserted=counters.inserted,
        updated=counters.updated,
        skipped=counters.skipped,
        deferred=deferred,
    )
