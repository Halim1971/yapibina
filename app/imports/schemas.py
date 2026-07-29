from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SiteRow:
    source_site_key: str
    site_name: str
    site_slug: str
    city: str
    district: str
    address_line: str
    is_active: bool
    payload_hash: str


@dataclass(frozen=True, slots=True)
class ResidentUnitRow:
    source_site_key: str
    source_unit_key: str
    block_name: str | None
    unit_number: str
    floor_label: str | None
    resident_source_key: str
    resident_full_name: str
    phone: str | None
    email: str
    is_active: bool
    payload_hash: str


@dataclass(frozen=True, slots=True)
class ChargeRow:
    source_site_key: str
    source_charge_key: str
    source_unit_key: str
    charge_date: date
    due_date: date
    period_year: int
    period_month: int
    charge_type: str
    title: str
    description: str | None
    amount: Decimal
    payload_hash: str


@dataclass(frozen=True, slots=True)
class PaymentRow:
    source_site_key: str
    source_payment_key: str
    source_unit_key: str
    payment_date: date
    payment_method: str
    amount: Decimal
    reference: str | None
    description: str | None
    payload_hash: str


@dataclass(frozen=True, slots=True)
class StandardPackage:
    root: Path
    dataset_name: str
    dataset_version: str
    schema_version: str
    manifest_sha256: str
    fingerprint: str
    sites: tuple[SiteRow, ...]
    units: tuple[ResidentUnitRow, ...]
    charges: tuple[ChargeRow, ...]
    payments: tuple[PaymentRow, ...]
    expense_count: int
    announcement_count: int


@dataclass(frozen=True, slots=True)
class ImportResult:
    run_id: str | None
    status: str
    fingerprint: str
    inserted: int
    updated: int
    skipped: int
    deferred: int
