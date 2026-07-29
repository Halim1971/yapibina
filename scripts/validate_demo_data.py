from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_data_lib import (
    DATE_RANGE_END,
    DATE_RANGE_START,
    MONTHS,
    SITE_SLUGS,
    read_workbook,
    sha256_file,
)
from scripts.generate_demo_data import DEFAULT_OUTPUT, generate_demo_data

CHARGE_TYPES = {"monthly_due", "additional_due", "manual"}
PAYMENT_METHODS = {"cash", "bank_transfer", "card", "other"}
EXPENSE_CATEGORIES = {
    "cleaning",
    "electricity",
    "water",
    "elevator_maintenance",
    "security",
    "landscaping",
    "management_service",
    "technical_maintenance",
    "insurance",
    "repair",
}
ANNOUNCEMENT_PRIORITIES = {"normal", "important", "urgent"}
PHONE_PATTERN = re.compile(r"^DEMO-05\d{2}-\d{3}-\d{2}-\d{2}$")


class DemoValidationError(RuntimeError):
    pass


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise DemoValidationError(f"{field}: geçersiz tarih {value!r}") from error
    raise DemoValidationError(f"{field}: tarih değeri bekleniyor.")


def _as_datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as error:
            raise DemoValidationError(
                f"{field}: geçersiz tarih-saat {value!r}"
            ) from error
    raise DemoValidationError(f"{field}: tarih-saat değeri bekleniyor.")


def _money(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise DemoValidationError(f"{field}: numeric tutar bekleniyor.")
    amount = Decimal(str(value))
    if amount <= 0 or amount.quantize(Decimal("0.01")) != amount:
        raise DemoValidationError(f"{field}: pozitif, iki ondalıklı tutar bekleniyor.")
    return amount.quantize(Decimal("0.01"))


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise DemoValidationError(f"{field}: integer değer bekleniyor.")
    try:
        return int(value)
    except (ValueError, TypeError) as error:
        raise DemoValidationError(f"{field}: integer değer bekleniyor.") from error


def _unique(rows: list[dict[str, Any]], field: str, label: str) -> set[str]:
    values = [str(row[field]) for row in rows]
    if len(values) != len(set(values)):
        raise DemoValidationError(f"{label}: {field} değerleri benzersiz değil.")
    return set(values)


def _validate_manifest(root: Path) -> dict[str, object]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise DemoValidationError("manifest.json bulunamadı.")
    manifest = cast(
        dict[str, object],
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )
    required = {
        "dataset_name",
        "dataset_version",
        "generated_at",
        "date_range_start",
        "date_range_end",
        "site_count",
        "unit_count",
        "resident_count",
        "currency",
        "generator_seed",
        "files",
        "schema_version",
    }
    missing = required - manifest.keys()
    if missing:
        raise DemoValidationError(f"Manifest alanları eksik: {sorted(missing)}")
    files = cast(list[dict[str, Any]], manifest["files"])
    for item in files:
        path = root / item["relative_path"]
        if not path.is_file():
            raise DemoValidationError(f"Manifest dosyası bulunamadı: {path}")
        rows = read_workbook(path)
        if len(rows) != item["row_count"]:
            raise DemoValidationError(f"Manifest satır sayısı hatalı: {path}")
        if sha256_file(path) != item["sha256"]:
            raise DemoValidationError(f"Manifest SHA-256 değeri hatalı: {path}")
    return manifest


def _validate_site_data(
    root: Path,
    slug: str,
    *,
    global_residents: set[str],
    global_charges: set[str],
    global_payments: set[str],
    global_expenses: set[str],
    global_announcements: set[str],
) -> None:
    site_dir = root / slug
    residents = read_workbook(site_dir / "residents_and_units.xlsx")
    charges = read_workbook(site_dir / "charges.xlsx")
    payments = read_workbook(site_dir / "payments.xlsx")
    expenses = read_workbook(site_dir / "expenses.xlsx")
    announcements = read_workbook(site_dir / "announcements.xlsx")
    if len(residents) != 10:
        raise DemoValidationError(f"{slug}: tam 10 bağımsız bölüm bekleniyor.")

    unit_keys = _unique(residents, "source_unit_key", slug)
    resident_keys = _unique(residents, "resident_source_key", slug)
    if global_residents & resident_keys:
        raise DemoValidationError(f"{slug}: resident source key global olarak yineleniyor.")
    global_residents.update(resident_keys)
    for row in residents:
        if row["access_role"] != "resident" or row["is_active"] is not True:
            raise DemoValidationError(f"{slug}: resident rolü/aktiflik hatalı.")
        if not str(row["email"]).endswith("@example.com"):
            raise DemoValidationError(f"{slug}: yalnız example.com e-posta kullanılabilir.")
        if PHONE_PATTERN.fullmatch(str(row["phone"])) is None:
            raise DemoValidationError(f"{slug}: telefon demo desenine uymuyor.")

    charge_keys = _unique(charges, "source_charge_key", slug)
    payment_keys = _unique(payments, "source_payment_key", slug)
    expense_keys = _unique(expenses, "source_expense_key", slug)
    announcement_keys = _unique(announcements, "source_announcement_key", slug)
    for seen, values, label in (
        (global_charges, charge_keys, "charge"),
        (global_payments, payment_keys, "payment"),
        (global_expenses, expense_keys, "expense"),
        (global_announcements, announcement_keys, "announcement"),
    ):
        if seen & values:
            raise DemoValidationError(f"{slug}: {label} source key global yineleniyor.")
        seen.update(values)

    months_by_unit: dict[str, set[int]] = defaultdict(set)
    charges_by_unit: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    payments_by_unit: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    monthly_amounts: dict[str, Decimal] = {}
    for row in charges:
        unit_key = str(row["source_unit_key"])
        if unit_key not in unit_keys:
            raise DemoValidationError(f"{slug}: charge unit referansı geçersiz.")
        charge_date = _as_date(row["charge_date"], "charge_date")
        due_date = _as_date(row["due_date"], "due_date")
        if not DATE_RANGE_START <= charge_date <= DATE_RANGE_END:
            raise DemoValidationError(f"{slug}: charge tarihi aralık dışında.")
        if not DATE_RANGE_START <= due_date <= DATE_RANGE_END:
            raise DemoValidationError(f"{slug}: due_date aralık dışında.")
        month = _integer(row["period_month"], "period_month")
        if _integer(row["period_year"], "period_year") != 2026 or month not in MONTHS:
            raise DemoValidationError(f"{slug}: charge dönemi geçersiz.")
        if row["charge_type"] not in CHARGE_TYPES or row["status"] != "posted":
            raise DemoValidationError(f"{slug}: charge enum değeri geçersiz.")
        if row["currency"] != "TRY":
            raise DemoValidationError(f"{slug}: charge currency TRY olmalıdır.")
        amount = _money(row["amount"], "charge amount")
        charges_by_unit[unit_key] += amount
        if row["charge_type"] == "monthly_due":
            months_by_unit[unit_key].add(month)
            monthly_amounts[unit_key] = amount
    if any(months != set(MONTHS) for months in months_by_unit.values()):
        raise DemoValidationError(f"{slug}: her daire için altı aylık aidat bulunmalı.")
    unit9 = f"{str(residents[8]['source_unit_key'])}"
    if not any(
        row["source_unit_key"] == unit9 and row["charge_type"] == "additional_due"
        for row in charges
    ):
        raise DemoValidationError(f"{slug}: ek aidat senaryosu bulunamadı.")

    payment_amounts: dict[str, list[Decimal]] = defaultdict(list)
    for row in payments:
        unit_key = str(row["source_unit_key"])
        if unit_key not in unit_keys:
            raise DemoValidationError(f"{slug}: payment unit referansı geçersiz.")
        payment_date = _as_date(row["payment_date"], "payment_date")
        if not DATE_RANGE_START <= payment_date <= DATE_RANGE_END:
            raise DemoValidationError(f"{slug}: payment tarihi aralık dışında.")
        if row["payment_method"] not in PAYMENT_METHODS or row["status"] != "posted":
            raise DemoValidationError(f"{slug}: payment enum değeri geçersiz.")
        if row["currency"] != "TRY":
            raise DemoValidationError(f"{slug}: payment currency TRY olmalıdır.")
        amount = _money(row["amount"], "payment amount")
        payments_by_unit[unit_key] += amount
        payment_amounts[unit_key].append(amount)

    ordered_units = [str(row["source_unit_key"]) for row in residents]
    standard = monthly_amounts[ordered_units[0]]
    if payments_by_unit[ordered_units[0]] != charges_by_unit[ordered_units[0]]:
        raise DemoValidationError(f"{slug}: tam ödeme senaryosu hatalı.")
    if charges_by_unit[ordered_units[2]] - payments_by_unit[ordered_units[2]] != standard / 2:
        raise DemoValidationError(f"{slug}: kısmi ödeme senaryosu hatalı.")
    if payments_by_unit[ordered_units[4]] <= charges_by_unit[ordered_units[4]]:
        raise DemoValidationError(f"{slug}: fazla ödeme senaryosu hatalı.")
    if charges_by_unit[ordered_units[6]] - payments_by_unit[ordered_units[6]] != standard * 2:
        raise DemoValidationError(f"{slug}: iki aylık borç senaryosu hatalı.")
    if max(payment_amounts[ordered_units[7]]) < standard * 3:
        raise DemoValidationError(f"{slug}: toplu ödeme senaryosu hatalı.")

    if len(expenses) < 18:
        raise DemoValidationError(f"{slug}: gider geçmişi yetersiz.")
    for row in expenses:
        if row["category"] not in EXPENSE_CATEGORIES or row["status"] != "posted":
            raise DemoValidationError(f"{slug}: gider enum değeri geçersiz.")
        if row["currency"] != "TRY":
            raise DemoValidationError(f"{slug}: gider currency TRY olmalıdır.")
        _money(row["amount"], "expense amount")
        if not DATE_RANGE_START <= _as_date(row["expense_date"], "expense_date") <= DATE_RANGE_END:
            raise DemoValidationError(f"{slug}: gider tarihi aralık dışında.")

    if len(announcements) < 6:
        raise DemoValidationError(f"{slug}: en az altı duyuru bekleniyor.")
    for row in announcements:
        published = _as_datetime(row["published_at"], "published_at")
        if published.utcoffset() is None:
            raise DemoValidationError(f"{slug}: published_at timezone içermelidir.")
        if not DATE_RANGE_START <= published.date() <= DATE_RANGE_END:
            raise DemoValidationError(f"{slug}: duyuru tarihi aralık dışında.")
        if row["priority"] not in ANNOUNCEMENT_PRIORITIES:
            raise DemoValidationError(f"{slug}: duyuru priority geçersiz.")


def _validate_determinism(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="yapibina-demo-check-") as temporary:
        generated = Path(temporary) / "demo_data"
        generate_demo_data(generated)
        expected = {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        actual = {
            path.relative_to(generated): path.read_bytes()
            for path in generated.rglob("*")
            if path.is_file()
        }
        if expected != actual:
            raise DemoValidationError("Generator çıktısı deterministik değil.")


def validate_demo_data(root: Path, *, check_determinism: bool = True) -> None:
    resolved = root.resolve()
    manifest = _validate_manifest(resolved)
    sites = read_workbook(resolved / "sites.xlsx")
    if len(sites) != 5 or manifest["site_count"] != 5:
        raise DemoValidationError("Dataset tam beş site içermelidir.")
    if {row["site_slug"] for row in sites} != set(SITE_SLUGS):
        raise DemoValidationError("Site slug listesi beklenen değerlerle eşleşmiyor.")
    _unique(sites, "source_site_key", "sites")
    _unique(sites, "site_slug", "sites")
    if any(row["currency"] != "TRY" or row["is_active"] is not True for row in sites):
        raise DemoValidationError("Site currency/aktiflik değeri hatalı.")

    residents: set[str] = set()
    charges: set[str] = set()
    payments: set[str] = set()
    expenses: set[str] = set()
    announcements: set[str] = set()
    for slug in SITE_SLUGS:
        _validate_site_data(
            resolved,
            slug,
            global_residents=residents,
            global_charges=charges,
            global_payments=payments,
            global_expenses=expenses,
            global_announcements=announcements,
        )
    if len(residents) != 50 or manifest["resident_count"] != 50:
        raise DemoValidationError("Dataset tam 50 resident içermelidir.")
    if manifest["unit_count"] != 50:
        raise DemoValidationError("Manifest unit_count 50 olmalıdır.")
    if check_determinism:
        _validate_determinism(resolved)


def main() -> int:
    parser = argparse.ArgumentParser(description="Yapıbina demo paketini doğrular.")
    parser.add_argument("--path", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--skip-determinism",
        action="store_true",
        help="İkinci üretim ile byte karşılaştırmasını atlar.",
    )
    arguments = parser.parse_args()
    try:
        validate_demo_data(
            arguments.path,
            check_determinism=not arguments.skip_determinism,
        )
    except (DemoValidationError, OSError, ValueError, KeyError) as error:
        print(f"Demo veri doğrulaması başarısız: {error}")
        return 1
    print(f"Demo veri paketi doğrulandı: {arguments.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
