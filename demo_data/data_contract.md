# Yapıbina standart Excel veri sözleşmesi

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
