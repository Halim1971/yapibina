from pathlib import Path

from flask import Flask
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.extensions import db

EXPECTED_TABLES = {
    "users",
    "organizations",
    "organization_brandings",
    "organization_domains",
    "organization_memberships",
    "buildings",
    "building_memberships",
    "apartments",
    "apartment_memberships",
    "charge_batches",
    "charges",
    "payments",
    "payment_allocations",
    "import_runs",
    "external_record_maps",
}


def test_metadata_contains_only_expected_core_tables(app: Flask) -> None:
    del app

    assert set(db.metadata.tables) == EXPECTED_TABLES


def test_core_foreign_keys_and_unique_constraints_exist(app: Flask) -> None:
    del app
    apartment = db.metadata.tables["apartments"]
    domain = db.metadata.tables["organization_domains"]
    building = db.metadata.tables["buildings"]

    assert any(
        isinstance(constraint, ForeignKeyConstraint)
        and set(constraint.column_keys) == {"organization_id", "building_id"}
        for constraint in apartment.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns}
        == {"organization_id", "code"}
        for constraint in building.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["hostname"]
        for constraint in domain.constraints
    )


def test_initial_migration_exists() -> None:
    versions = list(Path("migrations/versions").glob("*_create_tenant_core_models.py"))

    assert len(versions) == 1


def test_financial_migration_exists() -> None:
    versions = list(Path("migrations/versions").glob("*_add_charge_and_payment_core.py"))

    assert len(versions) == 1


def test_import_tracking_migration_and_source_key_constraint_exist() -> None:
    versions = list(
        Path("migrations/versions").glob("*_add_standard_data_import_tracking.py")
    )
    mapping = db.metadata.tables["external_record_maps"]

    assert len(versions) == 1
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns}
        == {"organization_id", "source_system", "entity_type", "source_key"}
        for constraint in mapping.constraints
    )
