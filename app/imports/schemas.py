from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    initial_password: str | None
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
    target_charge_source_key: str | None
    payload_hash: str


@dataclass(frozen=True, slots=True)
class ExpenseRow:
    source_site_key: str
    source_expense_key: str
    expense_date: date
    expense_month: date
    category: str
    description: str
    payment_method: str
    amount: Decimal
    contributions: tuple[tuple[str, Decimal], ...]
    payload_hash: str


@dataclass(frozen=True, slots=True)
class BankTransactionRow:
    source_site_key: str
    source_transaction_key: str
    transaction_date: date
    description: str
    transaction_type: str
    inflow: Decimal
    outflow: Decimal
    balance: Decimal
    category: str
    reference: str
    payload_hash: str


@dataclass(frozen=True, slots=True)
class DemoAnnouncementRow:
    source_site_key: str
    source_announcement_key: str
    title: str
    body: str
    published_at: datetime
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
    expenses: tuple[ExpenseRow, ...] = ()
    bank_transactions: tuple[BankTransactionRow, ...] = ()
    demo_announcements: tuple[DemoAnnouncementRow, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportResult:
    run_id: str | None
    status: str
    fingerprint: str
    inserted: int
    updated: int
    skipped: int
    deferred: int
