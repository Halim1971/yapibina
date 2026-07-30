from pathlib import Path

from sqlalchemy import func, select

from app.extensions import db
from app.imports.constants import SOURCE_SYSTEM_STANDARD_EXCEL
from app.imports.reader import read_standard_package, validate_package_relationships
from app.imports.service import import_standard_package
from app.models import (
    Announcement,
    Apartment,
    Building,
    BuildingBankTransaction,
    BuildingExpense,
    Charge,
    Organization,
    OrganizationStatus,
    Payment,
    User,
)
from app.services.resident_announcements import list_resident_announcements
from app.services.resident_finances import (
    get_monthly_due_detail,
    get_monthly_due_summary,
    list_resident_bank_movements,
    list_resident_expenses,
)


def _package_path() -> Path:
    return Path(__file__).parents[2] / "deneme"


def test_five_building_workbooks_are_imported_and_tenant_scoped(app: object) -> None:
    del app
    package = read_standard_package(_package_path())
    validate_package_relationships(package)
    assert (
        len(package.sites),
        len(package.units),
        len(package.charges),
        len(package.expenses),
        len(package.bank_transactions),
        len(package.demo_announcements),
    ) == (5, 47, 329, 210, 445, 15)

    organization = Organization(
        name="Demo Yönetim",
        slug="demo-yonetim",
        status=OrganizationStatus.ACTIVE,
    )
    db.session.add(organization)
    db.session.commit()
    result = import_standard_package(
        db.session,
        organization_id=organization.id,
        package=package,
        source_system=SOURCE_SYSTEM_STANDARD_EXCEL,
    )
    assert result.status == "completed"
    assert result.deferred == 0
    assert db.session.scalar(select(func.count()).select_from(Building)) == 5
    assert db.session.scalar(select(func.count()).select_from(Apartment)) == 47
    assert db.session.scalar(select(func.count()).select_from(Charge)) == 329
    assert db.session.scalar(select(func.count()).select_from(Payment)) == 300
    assert db.session.scalar(select(func.count()).select_from(BuildingExpense)) == 210
    assert (
        db.session.scalar(select(func.count()).select_from(BuildingBankTransaction))
        == 445
    )
    assert db.session.scalar(select(func.count()).select_from(Announcement)) == 15

    resident = db.session.scalar(
        select(User).where(User.email == "b001-r001@example.com")
    )
    apartment = db.session.scalar(
        select(Apartment)
        .join(Building, Building.id == Apartment.building_id)
        .where(Building.code == "B001", Apartment.number == "1")
    )
    assert resident is not None and resident.check_password("YapibinaDemo2026!")
    assert apartment is not None

    summary = get_monthly_due_summary(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
    )
    assert len(summary) == 6
    detail = get_monthly_due_detail(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
        year=summary[0].year,
        month=summary[0].month,
    )
    component_total = sum(
        (amount for _, amount in detail.items), start=detail.charged * 0
    )
    assert abs(component_total - detail.charged) <= detail.charged.__class__("0.05")
    bank_items, bank_total = list_resident_bank_movements(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        building_id=apartment.building_id,
        page=1,
        per_page=20,
    )
    expense_items, expense_total = list_resident_expenses(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        apartment_id=apartment.id,
        page=1,
        per_page=20,
    )
    assert bank_items and bank_total == 75
    assert expense_items and expense_total == 42
    announcements = list_resident_announcements(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        include_scheduled=True,
    )
    assert [item.status_label for item in announcements.items] == [
        "Planlandı",
        "Gönderildi",
        "Gönderildi",
    ]

    repeated = import_standard_package(
        db.session,
        organization_id=organization.id,
        package=package,
        source_system=SOURCE_SYSTEM_STANDARD_EXCEL,
    )
    assert repeated.status == "already_imported"
