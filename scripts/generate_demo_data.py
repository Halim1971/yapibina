from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_data_lib import (
    DATASET_VERSION,
    DATE_RANGE_END,
    DATE_RANGE_START,
    GENERATED_AT,
    GENERATOR_SEED,
    MONTHS,
    SCHEMA_VERSION,
    CellValue,
    Row,
    sha256_file,
    write_json,
    write_workbook,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "demo_data"

SITES = (
    ("SITE-001", "Ulubatlı Sitesi", "ulubatli-sitesi", "Fatih", "Vatan Demo Caddesi 10", 1250),
    (
        "SITE-002",
        "Çınarpark Apartmanı",
        "cinarpark-apartmani",
        "Üsküdar",
        "Kurgusal Çınar Sokak 22",
        1500,
    ),
    (
        "SITE-003",
        "Mavişehir Konutları",
        "mavisehir-konutlari",
        "Maltepe",
        "Örnek Sahil Yolu 35",
        1750,
    ),
    (
        "SITE-004",
        "Ihlamur Residence",
        "ihlamur-residence",
        "Şişli",
        "Demo Ihlamur Caddesi 8",
        2000,
    ),
    (
        "SITE-005",
        "Güneş Evleri",
        "gunes-evleri",
        "Bakırköy",
        "Kurgusal Güneş Sokak 14",
        2250,
    ),
)
FIRST_NAMES = (
    "Deniz",
    "Ekin",
    "Pınar",
    "Barış",
    "Derya",
    "Mert",
    "Selin",
    "Ozan",
    "İpek",
    "Bora",
)
LAST_NAMES = ("Örnek", "Kurgusal", "Temsili", "Deneme", "Demo")
MONTH_NAMES = {
    2: "Şubat",
    3: "Mart",
    4: "Nisan",
    5: "Mayıs",
    6: "Haziran",
    7: "Temmuz",
}

SITE_COLUMNS = (
    "source_site_key",
    "site_name",
    "site_slug",
    "city",
    "district",
    "address_line",
    "currency",
    "is_active",
)
RESIDENT_COLUMNS = (
    "source_unit_key",
    "block_name",
    "unit_number",
    "floor_label",
    "resident_source_key",
    "resident_full_name",
    "phone",
    "email",
    "access_role",
    "is_active",
)
CHARGE_COLUMNS = (
    "source_charge_key",
    "source_unit_key",
    "charge_date",
    "due_date",
    "period_year",
    "period_month",
    "charge_type",
    "title",
    "description",
    "amount",
    "currency",
    "status",
)
PAYMENT_COLUMNS = (
    "source_payment_key",
    "source_unit_key",
    "payment_date",
    "payment_method",
    "amount",
    "currency",
    "reference",
    "description",
    "status",
)
EXPENSE_COLUMNS = (
    "source_expense_key",
    "expense_date",
    "category",
    "vendor_name",
    "description",
    "amount",
    "currency",
    "document_number",
    "status",
)
ANNOUNCEMENT_COLUMNS = (
    "source_announcement_key",
    "published_at",
    "title",
    "body",
    "priority",
    "valid_until",
    "is_active",
)


def _safe_reset(output: Path) -> None:
    resolved = output.resolve()
    forbidden = {Path("/"), Path.home().resolve(), PROJECT_ROOT.resolve()}
    if resolved in forbidden or resolved.parent == resolved:
        raise ValueError(f"Güvenli olmayan çıktı dizini: {resolved}")
    if resolved.exists():
        if resolved.is_symlink():
            raise ValueError("Çıktı dizini symbolic link olamaz.")
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def _site_rows() -> list[Row]:
    return [
        {
            "source_site_key": key,
            "site_name": name,
            "site_slug": slug,
            "city": "İstanbul",
            "district": district,
            "address_line": address,
            "currency": "TRY",
            "is_active": True,
        }
        for key, name, slug, district, address, _ in SITES
    ]


def _residents(site_index: int, site_key: str) -> list[Row]:
    rows: list[Row] = []
    for unit_index in range(1, 11):
        global_index = site_index * 10 + unit_index
        rows.append(
            {
                "source_unit_key": f"{site_key}-UNIT-{unit_index:02d}",
                "block_name": "A" if unit_index <= 5 else "B",
                "unit_number": str(unit_index),
                "floor_label": str((unit_index - 1) // 2),
                "resident_source_key": f"RES-DEMO-{global_index:03d}",
                "resident_full_name": (
                    f"{FIRST_NAMES[unit_index - 1]} {LAST_NAMES[site_index]}"
                ),
                "phone": f"DEMO-0500-{global_index:03d}-00-00",
                "email": f"resident{global_index:03d}@example.com",
                "access_role": "resident",
                "is_active": True,
            }
        )
    return rows


def _charges(site_key: str, monthly_amount: int) -> list[Row]:
    rows: list[Row] = []
    for unit_index in range(1, 11):
        unit_key = f"{site_key}-UNIT-{unit_index:02d}"
        for month in MONTHS:
            rows.append(
                {
                    "source_charge_key": (
                        f"{site_key}-CHG-{unit_index:02d}-2026-{month:02d}"
                    ),
                    "source_unit_key": unit_key,
                    "charge_date": date(2026, month, 1),
                    "due_date": date(2026, month, 15),
                    "period_year": 2026,
                    "period_month": month,
                    "charge_type": "monthly_due",
                    "title": f"{MONTH_NAMES[month]} 2026 Aidatı",
                    "description": "Aylık ortak gider aidatı",
                    "amount": Decimal(monthly_amount).quantize(Decimal("0.00")),
                    "currency": "TRY",
                    "status": "posted",
                }
            )
        if unit_index == 9:
            rows.append(
                {
                    "source_charge_key": f"{site_key}-CHG-{unit_index:02d}-EK-2026-05",
                    "source_unit_key": unit_key,
                    "charge_date": date(2026, 5, 5),
                    "due_date": date(2026, 5, 25),
                    "period_year": 2026,
                    "period_month": 5,
                    "charge_type": "additional_due",
                    "title": "Asansör yenileme ek aidatı",
                    "description": "Kontrollü demo ek aidat kaydı",
                    "amount": Decimal(monthly_amount // 2).quantize(Decimal("0.00")),
                    "currency": "TRY",
                    "status": "posted",
                }
            )
    return rows


def _payment_months(unit_index: int) -> list[tuple[int, Decimal, int]]:
    if unit_index == 1:
        return [(month, Decimal("1.00"), 12) for month in MONTHS]
    if unit_index == 2:
        return [(month, Decimal("1.00"), 13) for month in range(2, 7)]
    if unit_index == 3:
        return [
            *[(month, Decimal("1.00"), 14) for month in range(2, 7)],
            (7, Decimal("0.50"), 18),
        ]
    if unit_index == 4:
        return [
            *[(month, Decimal("1.00"), 11) for month in range(2, 6)],
            (7, Decimal("1.00"), 20),
        ]
    if unit_index == 5:
        return [
            *[(month, Decimal("1.00"), 10) for month in MONTHS],
            (7, Decimal("0.40"), 25),
        ]
    if unit_index == 6:
        return [
            (2, Decimal("1.00"), 25),
            (3, Decimal("1.00"), 8),
            (4, Decimal("1.00"), 28),
            (5, Decimal("1.00"), 21),
            (6, Decimal("1.00"), 9),
            (7, Decimal("1.00"), 30),
        ]
    if unit_index == 7:
        return [(month, Decimal("1.00"), 16) for month in range(2, 6)]
    if unit_index == 8:
        return [
            (2, Decimal("1.00"), 15),
            (3, Decimal("1.00"), 15),
            (4, Decimal("1.00"), 15),
            (7, Decimal("3.00"), 22),
        ]
    if unit_index == 9:
        return [(month, Decimal("1.00"), 12) for month in MONTHS]
    return [(2, Decimal("1.00"), 19), (3, Decimal("1.00"), 24)]


def _payments(site_key: str, monthly_amount: int) -> list[Row]:
    rows: list[Row] = []
    for unit_index in range(1, 11):
        unit_key = f"{site_key}-UNIT-{unit_index:02d}"
        for sequence, (month, multiplier, day) in enumerate(
            _payment_months(unit_index),
            start=1,
        ):
            amount = (Decimal(monthly_amount) * multiplier).quantize(
                Decimal("0.00")
            )
            rows.append(
                {
                    "source_payment_key": (
                        f"{site_key}-PAY-{unit_index:02d}-{sequence:02d}"
                    ),
                    "source_unit_key": unit_key,
                    "payment_date": date(2026, month, day),
                    "payment_method": (
                        "bank_transfer"
                        if unit_index % 3
                        else "cash"
                    ),
                    "amount": amount,
                    "currency": "TRY",
                    "reference": f"DEMO-{site_key[:4].upper()}-{unit_index:02d}-{sequence:02d}",
                    "description": (
                        "Toplu dönem ödemesi"
                        if multiplier >= Decimal("2.00")
                        else "Demo aidat ödemesi"
                    ),
                    "status": "posted",
                }
            )
    return rows


def _expenses(
    site_index: int,
    site_key: str,
    monthly_amount: int,
    rng: random.Random,
) -> list[Row]:
    recurring = (
        ("cleaning", "Demo Temizlik Hizmetleri", Decimal("0.80")),
        ("electricity", "Örnek Enerji", Decimal("0.45")),
        ("elevator_maintenance", "Kurgusal Asansör Servisi", Decimal("0.35")),
    )
    variable = (
        ("water", "Örnek Su Hizmeti", "Ortak alan su tüketimi"),
        ("landscaping", "Demo Peyzaj", "Bahçe bakım çalışması"),
        ("repair", "Kurgusal Teknik", "Ortak alan küçük onarımı"),
        ("insurance", "Örnek Sigorta", "Bina ortak alan sigortası"),
        ("technical_maintenance", "Demo Teknik", "Periyodik teknik bakım"),
    )
    rows: list[Row] = []
    sequence = 0
    for month in MONTHS:
        for category, vendor, ratio in recurring:
            sequence += 1
            variation = Decimal(rng.randint(-75, 125))
            amount = (
                Decimal(monthly_amount) * ratio + variation + site_index * 25
            ).quantize(Decimal("0.00"))
            rows.append(
                {
                    "source_expense_key": f"{site_key}-EXP-{sequence:03d}",
                    "expense_date": date(2026, month, 5 + sequence % 14),
                    "category": category,
                    "vendor_name": vendor,
                    "description": f"{month}. ay düzenli ortak alan gideri",
                    "amount": amount,
                    "currency": "TRY",
                    "document_number": f"DEMO-FTR-{site_index + 1:02d}-{sequence:03d}",
                    "status": "posted",
                }
            )
        category, vendor, description = variable[(month + site_index) % len(variable)]
        sequence += 1
        rows.append(
            {
                "source_expense_key": f"{site_key}-EXP-{sequence:03d}",
                "expense_date": date(2026, month, 20),
                "category": category,
                "vendor_name": vendor,
                "description": description,
                "amount": (
                    Decimal(monthly_amount)
                    * Decimal("1.10")
                    + Decimal(rng.randint(100, 600))
                ).quantize(Decimal("0.00")),
                "currency": "TRY",
                "document_number": f"DEMO-FTR-{site_index + 1:02d}-{sequence:03d}",
                "status": "posted",
            }
        )
    return rows


def _announcements(site_key: str) -> list[Row]:
    topics = (
        (
            "Su kesintisi",
            "Ortak su hattındaki çalışma nedeniyle 10.00-13.00 arasında su kesilecektir.",
            "important",
        ),
        (
            "Asansör bakımı",
            "Asansörlerin planlı bakımı cuma günü yapılacaktır.",
            "normal",
        ),
        (
            "Genel kurul",
            "Olağan genel kurul toplantısı yönetim salonunda gerçekleştirilecektir.",
            "important",
        ),
        (
            "Otopark düzenlemesi",
            "Misafir araçlarının ayrılmış alanları kullanması rica olunur.",
            "normal",
        ),
        (
            "İlaçlama",
            "Ortak alan ilaçlaması sırasında çocukların alanlardan uzak tutulması rica olunur.",
            "urgent",
        ),
        (
            "Aidat son ödeme hatırlatması",
            "Aidat ödemelerinin ayın 15'ine kadar tamamlanması rica olunur.",
            "normal",
        ),
        (
            "Ortak alan çalışması",
            "Bahçe girişindeki zemin yenileme çalışması iki gün sürecektir.",
            "important",
        ),
    )
    rows: list[Row] = []
    for index, (title, body, priority) in enumerate(topics, start=1):
        published = datetime(
            2026,
            min(index + 1, 7),
            min(3 + index * 2, 25),
            9,
            30,
            tzinfo=timezone(timedelta(hours=3)),
        )
        valid_until = min(
            published.date() + timedelta(days=20),
            DATE_RANGE_END,
        )
        rows.append(
            {
                "source_announcement_key": f"{site_key}-ANN-{index:02d}",
                "published_at": published.isoformat(),
                "title": title,
                "body": body,
                "priority": priority,
                "valid_until": valid_until,
                "is_active": valid_until >= date(2026, 7, 20),
            }
        )
    return rows


def _readme() -> str:
    return """# Yapıbina demo veri paketi

Bu dizindeki veriler tamamen kurgusaldır. İsimler temsili olarak üretilmiş,
telefonlar `DEMO-` öneki taşımakta ve tüm e-postalar `example.com` alan adını
kullanmaktadır.

Yapıbina, Apsiyon'un yerine geçen bir operasyon veya muhasebe sistemi değildir.
Bu paket Apsiyon adapter'ından bağımsız Yapıbina standart ara veri formatını
örnekler. Dosyalar henüz uygulama veritabanına import edilmemektedir ve gerçek
Apsiyon adapter'ı ya da tarayıcı otomasyonu mevcut değildir.

Üretim ve doğrulama:

```bash
python scripts/generate_demo_data.py
python scripts/validate_demo_data.py
python scripts/validate_demo_data.py --path demo_data
```

Paket 1 Şubat–31 Temmuz 2026 arasında beş kurgusal site, 50 bağımsız bölüm,
50 resident, aidat/ödeme senaryoları, giderler ve duyurular içerir.
"""


def _contract() -> str:
    return """# Yapıbina standart Excel veri sözleşmesi

## Genel kurallar

- Format adapter bağımsızdır; Apsiyon kolon adları bu sözleşmeye taşınmaz.
- Tarih `YYYY-MM-DD`, tarih-saat `YYYY-MM-DDTHH:MM:SS+03:00` anlamındadır.
- Excel tarih hücreleri gerçek date/datetime, tutarlar numeric ve iki ondalıktır.
- Para birimi yalnız `TRY`; boolean hücreler gerçek boolean değeridir.
- `source_*_key` değerleri kaynak kapsamında stabil idempotency anahtarlarıdır.
- Dosyalar formül, makro, gizli sheet ve birleştirilmiş hücre içermez.

## sites.xlsx

Tam liste/snapshot dosyasıdır. Zorunlu ve null olamaz: `source_site_key`
(string, unique), `site_name` (string), `site_slug` (string, unique), `city`,
`district`, `address_line` (string), `currency` (`TRY`), `is_active` (boolean).
Eksik site, importer politikası açıkça onaylanmadan otomatik silinmez.

## residents_and_units.xlsx

Site başına tam liste/snapshot dosyasıdır. Zorunlu ve null olamaz:
`source_unit_key` (site içinde unique), `resident_source_key` (global unique),
`unit_number`, `resident_full_name`, `phone`, `email`, `access_role`
(`resident`), `is_active` (boolean). `block_name` ve `floor_label` opsiyonel
string alanlardır. Malik/kiracı tarihçesi veya ownership anlamı taşımaz.

## charges.xlsx

Append/upsert hareket listesidir. `source_charge_key` global unique,
`source_unit_key` residents dosyasına referans, `charge_date`, `due_date`
(date), `period_year` (integer), `period_month` (1–12), `charge_type`
(`monthly_due|additional_due|manual`), `title`, `amount` (numeric > 0),
`currency` (`TRY`) ve `status` (`posted`) zorunludur. `description`
opsiyoneldir. Aynı source key tekrarında idempotent update beklenir.

## payments.xlsx

Append/upsert hareket listesidir. `source_payment_key` global unique,
`source_unit_key` referansı, `payment_date`, `payment_method`
(`cash|bank_transfer|card|other`), `amount` (numeric > 0), `currency` (`TRY`)
ve `status` (`posted`) zorunludur. `reference` ve `description` opsiyoneldir.
Allocation dosyası yoktur; importer mevcut en eski açık borç yaklaşımını
uygular. Aynı source key idempotent işlenir.

## expenses.xlsx

Append/upsert hareket listesidir. `source_expense_key` global unique,
`expense_date`, `category` (`cleaning|electricity|water|elevator_maintenance|
security|landscaping|management_service|technical_maintenance|insurance|
repair`), `vendor_name`, `description`, `amount` (numeric > 0), `currency`
(`TRY`) ve `status` (`posted`) zorunludur. `document_number` opsiyoneldir.

## announcements.xlsx

Append/upsert listesidir. `source_announcement_key` global unique,
`published_at` (timezone-aware datetime), `title`, `body`, `priority`
(`normal|important|urgent`) ve `is_active` (boolean) zorunludur.
`valid_until` opsiyonel date alanıdır. Aynı source key idempotent işlenir.

## Senkronizasyon

Adapter önce kaynak raporunu bu sözleşmeye normalize eder. Importer source
keylerle upsert yapar, referansları doğrular ve dosyada görünmeyen hareketleri
silmez. Snapshot dosyalarında pasifleştirme ancak açık senkronizasyon politikası
ile yapılır. Kaynak rapor formatı değişirse yalnız adapter değişmelidir.
"""


def generate_demo_data(output_path: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    output = output_path.resolve()
    _safe_reset(output)
    rng = random.Random(GENERATOR_SEED)
    generated_files: list[dict[str, CellValue]] = []

    sites_path = output / "sites.xlsx"
    row_count = write_workbook(
        sites_path,
        sheet_name="sites",
        columns=SITE_COLUMNS,
        rows=_site_rows(),
    )
    generated_files.append(
        {
            "relative_path": "sites.xlsx",
            "row_count": row_count,
            "sha256": sha256_file(sites_path),
        }
    )

    for site_index, (site_key, _, slug, _, _, monthly_amount) in enumerate(SITES):
        site_dir = output / slug
        datasets = (
            (
                "residents_and_units.xlsx",
                "residents",
                RESIDENT_COLUMNS,
                _residents(site_index, site_key),
            ),
            ("charges.xlsx", "charges", CHARGE_COLUMNS, _charges(site_key, monthly_amount)),
            (
                "payments.xlsx",
                "payments",
                PAYMENT_COLUMNS,
                _payments(site_key, monthly_amount),
            ),
            (
                "expenses.xlsx",
                "expenses",
                EXPENSE_COLUMNS,
                _expenses(site_index, site_key, monthly_amount, rng),
            ),
            (
                "announcements.xlsx",
                "announcements",
                ANNOUNCEMENT_COLUMNS,
                _announcements(site_key),
            ),
        )
        for filename, sheet_name, columns, rows in datasets:
            path = site_dir / filename
            count = write_workbook(
                path,
                sheet_name=sheet_name,
                columns=columns,
                rows=rows,
            )
            generated_files.append(
                {
                    "relative_path": path.relative_to(output).as_posix(),
                    "row_count": count,
                    "sha256": sha256_file(path),
                }
            )

    (output / "README.md").write_text(_readme(), encoding="utf-8")
    (output / "data_contract.md").write_text(_contract(), encoding="utf-8")
    manifest: dict[str, object] = {
        "dataset_name": "Yapıbina Kontrollü Demo Veri Paketi",
        "dataset_version": DATASET_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "date_range_start": DATE_RANGE_START.isoformat(),
        "date_range_end": DATE_RANGE_END.isoformat(),
        "site_count": 5,
        "unit_count": 50,
        "resident_count": 50,
        "currency": "TRY",
        "generator_seed": GENERATOR_SEED,
        "files": generated_files,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Yapıbina demo Excel paketini üretir.")
    parser.add_argument("--path", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    manifest = generate_demo_data(arguments.path)
    print(
        f"Demo veri paketi üretildi: {arguments.path} "
        f"({manifest['site_count']} site, {manifest['unit_count']} daire)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
