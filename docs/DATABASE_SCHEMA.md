# Yapıbina Veritabanı Şeması

## 1. İlkeler

- PostgreSQL, tek veritabanı ve ortak schema kullanılır.
- Primary key'ler tahmin edilmesi güç UUID'dir; ID yine de yetki sınırı kabul edilmez.
- Zaman alanları `timestamptz` olarak UTC tutulur.
- Para `numeric(14,2)`, uygulamada `Decimal`; `float` yasaktır.
- E-posta ve hostname normalize edilir; case-insensitive benzersizlik için `citext` veya `lower(...)` indeksleri değerlendirilebilir.
- Tenant tablolarında `organization_id NOT NULL` doğrudan bulunur.
- Kritik finansal ve audit kayıtları fiziksel silinmez.
- `created_at` ve `updated_at` çoğu mutable tabloda standarttır.

Enum benzeri alanlar PostgreSQL enum yerine doğrulamalı kısa metin/check constraint ile başlayabilir; böylece deployment sırasında enum migration zorluğu azaltılır.

## 2. Tenant kapsamı özeti

Doğrudan `organization_id` taşıması gereken tablolar:

`organization_domain`, `organization_branding`, `organization_membership`, `building`, `building_membership`, `apartment`, `apartment_membership`, `charge`, `payment`, `payment_allocation`, `bank_transaction`, `bank_import_batch`, `expense_category`, `expense`, `document`, `announcement`, `announcement_read`, `audit_log`.

`user` platform çapında kimlik kaydı olduğu için `organization_id` taşımaz. `organization` kendi tenant köküdür. Tenant tablosundaki `organization_id`, üst kayıttan türetilebilse bile defense-in-depth, sorgu güvenliği ve indeksleme için saklanır. Tutarlılık service kuralları ve uygun birleşik foreign key/constraint'lerle korunur.

## 3. Tablolar

### `organization`

Tenant ve yönetim firması kaydı.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `name` | varchar(160) | NOT NULL |
| `legal_name` | varchar(240) | nullable |
| `status` | varchar(20) | NOT NULL, `active/suspended/closed` check |
| `plan_code` | varchar(50) | nullable; paket kataloğu netleşene kadar |
| `default_currency` | char(3) | NOT NULL, default `TRY` |
| `timezone` | varchar(64) | NOT NULL, default `Europe/Istanbul` |
| `locale` | varchar(16) | NOT NULL, default `tr-TR` |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

İndeks: `(status)`. Organization adı global unique olmak zorunda değildir.

### `organization_domain`

Tenant'a ulaşan geçici veya özel hostname kayıtları.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK organization, NOT NULL |
| `hostname` | varchar(253) | NOT NULL, normalize edilmiş |
| `domain_type` | varchar(20) | `platform_subdomain/custom` |
| `status` | varchar(20) | `pending/awaiting_dns/dns_verified/ssl_pending/active/failed/suspended`; NOT NULL |
| `verification_token_hash` | varchar(255) | nullable; ham token saklanmaz |
| `verified_at` | timestamptz | nullable |
| `ssl_status` | varchar(20) | `not_requested/pending/ready/failed/expired` |
| `is_primary` | boolean | NOT NULL default false |
| `is_active` | boolean | NOT NULL default false |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: normalize edilmiş `hostname` global unique. Partial unique: organization başına `WHERE is_primary AND is_active` tek kayıt. İndeksler: `(organization_id, status)`, `(organization_id, is_active)`. `is_active=true` yalnız `status=active`, SSL ready ve organization aktifken geçerlidir.

### `organization_branding`

Organization'ın tekil marka ve tema ayarları.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL, UNIQUE |
| `display_name` | varchar(160) | nullable |
| `legal_name` | varchar(240) | nullable |
| `logo_document_id` | uuid | FK document, nullable |
| `small_logo_document_id` | uuid | FK document, nullable |
| `favicon_document_id` | uuid | FK document, nullable |
| `primary_color` | varchar(7) | nullable, hex check |
| `secondary_color` | varchar(7) | nullable, hex check |
| `surface_color` | varchar(7) | nullable, hex check |
| `panel_title` | varchar(120) | nullable |
| `login_message` | varchar(500) | nullable |
| `support_email` | varchar(254) | nullable |
| `phone` | varchar(40) | nullable |
| `website_url` | varchar(500) | nullable |
| `white_label_enabled` | boolean | NOT NULL default false |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Logo FK'lerinde döngüsel migration sırası dikkate alınır; alternatif olarak branding asset ilişkisi ayrı tabloda kurulabilir.

### `user`

Platform çapında tekil kimlik. Tenant yetkisi burada tutulmaz.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `email` | varchar(254) | NOT NULL, normalize edilmiş |
| `password_hash` | varchar(255) | NOT NULL |
| `full_name` | varchar(160) | NOT NULL |
| `phone` | varchar(40) | nullable |
| `is_active` | boolean | NOT NULL default true |
| `is_platform_super_admin` | boolean | NOT NULL default false |
| `last_login_at` | timestamptz | nullable |
| `password_changed_at` | timestamptz | nullable |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: case-insensitive email. İndeks: `(is_active)`. Platform rolü daha sonra çoklu platform rolleri gerekirse ayrı role tablolarına taşınabilir.

### `organization_membership`

Kullanıcının organization kapsamındaki rolü.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `user_id` | uuid | FK user, NOT NULL |
| `role` | varchar(30) | başlangıçta `organization_admin`; check |
| `status` | varchar(20) | `invited/active/suspended/revoked` |
| `invited_at` | timestamptz | nullable |
| `joined_at` | timestamptz | nullable |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: `(organization_id, user_id, role)`. İndeksler: `(user_id, status)`, `(organization_id, status)`.

### `building`

Organization'a ait bina.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `name` | varchar(160) | NOT NULL |
| `code` | varchar(50) | nullable |
| `address_line` | varchar(300) | nullable |
| `district` | varchar(100) | nullable |
| `city` | varchar(100) | nullable |
| `postal_code` | varchar(20) | nullable |
| `is_active` | boolean | NOT NULL default true |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: `(organization_id, code)` yalnızca code doluyken. İndeks: `(organization_id, is_active)`.

### `building_membership`

Building manager ve gerektiğinde başka operasyon rollerinin bina ataması.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK building, NOT NULL |
| `user_id` | uuid | FK user, NOT NULL |
| `role` | varchar(30) | `building_manager` |
| `status` | varchar(20) | `active/revoked` |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: `(building_id, user_id, role)`. İndeksler: `(organization_id, user_id, status)`, `(building_id, status)`. Building'in aynı organization'a aitliği birleşik FK veya transaction kuralıyla korunur.

### `apartment`

Binadaki bağımsız bölüm.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK building, NOT NULL |
| `unit_number` | varchar(30) | NOT NULL |
| `floor_label` | varchar(30) | nullable |
| `share_ratio` | numeric(10,6) | nullable, non-negative check |
| `is_active` | boolean | NOT NULL default true |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: `(building_id, unit_number)`. İndeks: `(organization_id, building_id, is_active)`.

### `apartment_membership`

Kullanıcı-daire ilişkisi ve tarihsel erişim temeli.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `apartment_id` | uuid | FK apartment, NOT NULL |
| `user_id` | uuid | FK user, NOT NULL |
| `relationship_type` | varchar(20) | `owner/tenant/occupant/other` |
| `status` | varchar(20) | `invited/active/inactive/revoked`; NOT NULL |
| `starts_on` | date | NOT NULL |
| `ends_on` | date | nullable |
| `status_changed_by_user_id` | uuid | FK user, nullable |
| `status_changed_at` | timestamptz | nullable |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Bir dönem yalnız `status=active` iken erişim verir; `ends_on` geçmişteyse aktif kabul edilmez. Organization admin veya hedef binanın building manager'ı durumu değiştirebilir. Satır fiziksel silinmez; ilişki bitince `inactive` ve `ends_on` kullanılır. Aynı kullanıcı/daire için tarihsel birden çok dönem olabilir; aynı anda birden fazla aktif dönem partial unique constraint ile engellenir. İndeksler: `(organization_id, user_id, status)`, `(apartment_id, status)`, `(user_id, starts_on, ends_on)`.

### `charge`

Daireye tahakkuk ettirilmiş borç. Posted kayıt append-only'dir.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `apartment_id` | uuid | FK, NOT NULL |
| `charge_type` | varchar(20) | `aidat/ek_borc/duzeltme/diger`; NOT NULL |
| `amount` | numeric(14,2) | NOT NULL, `> 0` |
| `currency_code` | char(3) | NOT NULL default TRY |
| `charge_date` | date | NOT NULL |
| `due_date` | date | NOT NULL |
| `period_year` | smallint | nullable, makul yıl check |
| `period_month` | smallint | nullable, 1–12 check |
| `description` | varchar(500) | NOT NULL |
| `reference` | varchar(120) | nullable |
| `reversal_of_id` | uuid | self FK, nullable |
| `status` | varchar(20) | `posted/reversed`; NOT NULL |
| `idempotency_key` | varchar(100) | nullable |
| `created_by_user_id` | uuid | FK user, NOT NULL |
| `created_at` | timestamptz | NOT NULL |

Unique: `(organization_id, idempotency_key)` partial; `reversal_of_id` için tek ters kayıt partial unique. İndeksler: `(organization_id, apartment_id, due_date, status)`, `(organization_id, building_id, period_year, period_month)`, `(reversal_of_id)`. Ters kayıt aynı tenant/bina/daire/para birimindedir. Posted satırlar update/delete edilmez. Otomatik faiz/ceza yoktur; manuel veya toplu oluşturma aynı modeli kullanır.

### `payment`

Daireye kaydedilen ödeme veya onun ters kaydı. Dağıtılmamış kısmı daire kredisi/alacağıdır.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `apartment_id` | uuid | FK, NOT NULL |
| `amount` | numeric(14,2) | NOT NULL, `> 0` |
| `currency_code` | char(3) | NOT NULL default TRY |
| `payment_date` | date | NOT NULL |
| `description` | varchar(500) | NOT NULL |
| `reference` | varchar(120) | nullable |
| `reversal_of_id` | uuid | self FK, nullable |
| `status` | varchar(20) | `posted/reversed`; NOT NULL |
| `idempotency_key` | varchar(100) | nullable |
| `created_by_user_id` | uuid | FK user, NOT NULL |
| `created_at` | timestamptz | NOT NULL |

Unique: `(organization_id, idempotency_key)` partial ve `reversal_of_id` partial unique. İndeksler: `(organization_id, apartment_id, payment_date)`, `(reversal_of_id)`. Posted ödeme fiziksel olarak silinmez/değiştirilmez.

### `payment_allocation`

Bir ödemenin bir açık borca ayrılan kısmı; kısmi ve çoklu dağıtımı sağlar.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `apartment_id` | uuid | FK, NOT NULL |
| `payment_id` | uuid | FK payment, NOT NULL |
| `charge_id` | uuid | FK charge, NOT NULL |
| `amount` | numeric(14,2) | NOT NULL, `> 0` |
| `status` | varchar(20) | `active/reversed`; NOT NULL |
| `created_at` | timestamptz | NOT NULL |
| `reversed_at` | timestamptz | nullable |

Unique: `(payment_id, charge_id)` aktif kayıtlar için partial unique. İndeksler: `(organization_id, payment_id, status)`, `(organization_id, charge_id, status)`. Payment, charge ve allocation aynı organization/bina/daire/para biriminde olmalıdır. Aktif allocation toplamı payment tutarını ve charge açık tutarını aşamaz. Service bunu aynı transaction'da doğrular; commit anındaki yarışlara karşı PostgreSQL deferred constraint trigger kullanılır. Varsayılan service sırası: vadesi geçmiş borçlarda en eski `due_date`, sonra kalan açık borçlarda en eski `due_date`, eşitlikte `created_at/id`. `payment.amount - active allocation sum` dağıtılmamış kredi/alacak bakiyesidir.

### `bank_import_batch`

CSV/Excel içe aktarma denemesi ve izlenebilirliği.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `source_document_id` | uuid | FK document, nullable |
| `status` | varchar(20) | `uploaded/validated/imported/failed` |
| `row_count` | integer | non-negative |
| `imported_count` | integer | non-negative |
| `error_summary` | jsonb | nullable, hassas veri filtrelenmiş |
| `created_by_user_id` | uuid | FK user, NOT NULL |
| `created_at` | timestamptz | NOT NULL |
| `completed_at` | timestamptz | nullable |

İndeks: `(organization_id, building_id, created_at)`.

### `bank_transaction`

Manuel, dosyadan veya gelecekte provider'dan gelen bina banka hareketi.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `import_batch_id` | uuid | FK bank_import_batch, nullable |
| `transaction_date` | date | NOT NULL |
| `direction` | varchar(10) | `in/out` |
| `amount` | numeric(14,2) | NOT NULL, `> 0` |
| `currency_code` | char(3) | NOT NULL default TRY |
| `description` | varchar(500) | NOT NULL |
| `reference` | varchar(160) | nullable |
| `source_type` | varchar(20) | `manual/import/provider` |
| `provider_code` | varchar(50) | nullable |
| `external_id` | varchar(160) | nullable |
| `fingerprint` | varchar(128) | nullable |
| `created_by_user_id` | uuid | FK user, nullable |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: `(organization_id, provider_code, external_id)` partial. İndeksler: `(organization_id, building_id, transaction_date)`, `(import_batch_id)`, `(organization_id, fingerprint)`.

### `expense_category`

Organization'a ait gider kategorisi.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `name` | varchar(100) | NOT NULL |
| `is_active` | boolean | NOT NULL default true |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Unique: `(organization_id, name)` case-insensitive. İndeks: `(organization_id, is_active)`.

### `expense`

Bina gideri.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `category_id` | uuid | FK expense_category, NOT NULL |
| `bank_transaction_id` | uuid | FK bank_transaction, nullable |
| `description` | varchar(500) | NOT NULL |
| `amount` | numeric(14,2) | NOT NULL, `> 0` |
| `currency_code` | char(3) | NOT NULL default TRY |
| `expense_date` | date | NOT NULL |
| `vendor_name` | varchar(200) | nullable |
| `visibility` | varchar(20) | `residents/admin_only` |
| `status` | varchar(20) | `active/cancelled/archived` |
| `created_by_user_id` | uuid | FK user, NOT NULL |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

MVP'de `bank_transaction_id` nullable'dır; eşleştirme zorunlu değildir. Dolu değer için global/tenant güvenli partial unique constraint, bir banka hareketinin en fazla bir gidere bağlanmasını sağlar. Expense üzerinde tek FK bulunması bir giderin de en fazla bir harekete bağlanmasını sağlar. İlişki aynı organization ve building içinde olmalıdır. Kısmi/bölünmüş/çoklu mutabakat MVP dışıdır; ileride bu FK kontrollü migration ile junction/reconciliation tablosuna taşınabilir. İndeksler: `(organization_id, building_id, expense_date)`, `(category_id)`.

### `document`

Dosyanın metadata ve yetki kapsamı. Binary içerik storage adapter'dadır.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, nullable |
| `expense_id` | uuid | FK expense, nullable |
| `document_type` | varchar(30) | `expense_invoice/branding/bank_import/other` |
| `storage_provider` | varchar(30) | NOT NULL |
| `storage_key` | varchar(500) | NOT NULL |
| `original_filename` | varchar(255) | NOT NULL, gösterim amaçlı |
| `safe_filename` | varchar(255) | NOT NULL |
| `mime_type` | varchar(150) | NOT NULL |
| `size_bytes` | bigint | NOT NULL, positive check |
| `checksum_sha256` | char(64) | NOT NULL |
| `scan_status` | varchar(20) | `not_required/pending/clean/rejected/failed` |
| `status` | varchar(20) | `active/archived/deleted` |
| `uploaded_by_user_id` | uuid | FK user, NOT NULL |
| `created_at` | timestamptz | NOT NULL |
| `archived_at` | timestamptz | nullable |

Unique: `(storage_provider, storage_key)`. İndeksler: `(organization_id, building_id, created_at)`, `(organization_id, expense_id)`, `(scan_status)`.

MVP doğrulamaları: yalnız PDF (`application/pdf`), JPG/JPEG (`image/jpeg`) ve PNG (`image/png`); en fazla `10 * 1024 * 1024` byte. Uzantı ve MIME birlikte doğrulanır, storage key rastgele/güvenlidir ve `original_filename` hiçbir zaman disk yolu olmaz. Harici malware taraması zorunlu değildir; `scan_status` ve adapter/hook alanı daha sonra entegrasyonu mümkün kılar. Otomatik fiziksel silme yapılmaz.

### `announcement`

Bina duyurusu.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `building_id` | uuid | FK, NOT NULL |
| `title` | varchar(200) | NOT NULL |
| `content` | text | NOT NULL, güvenli düz metin/sanitize edilmiş |
| `status` | varchar(20) | `draft/published/expired/archived` |
| `published_at` | timestamptz | nullable |
| `valid_until` | timestamptz | nullable |
| `created_by_user_id` | uuid | FK user, NOT NULL |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

İndeksler: `(organization_id, building_id, status, published_at)`, `(valid_until)`.

### `announcement_read`

Kullanıcının duyuruyu okuma kaydı.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, NOT NULL |
| `announcement_id` | uuid | FK announcement, NOT NULL |
| `user_id` | uuid | FK user, NOT NULL |
| `read_at` | timestamptz | NOT NULL |

Unique: `(announcement_id, user_id)`. İndeks: `(organization_id, user_id, read_at)`.

### `audit_log`

Kritik eylemlerin append-only izi.

| Alan | Tür | Kurallar |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK, nullable yalnızca platform-global eylemlerde |
| `actor_user_id` | uuid | FK user, nullable sistem eyleminde |
| `action` | varchar(100) | NOT NULL |
| `entity_type` | varchar(100) | NOT NULL |
| `entity_id` | uuid | nullable |
| `old_values` | jsonb | nullable, secret filtrelenmiş |
| `new_values` | jsonb | nullable, secret filtrelenmiş |
| `ip_address` | inet | nullable |
| `user_agent` | varchar(500) | nullable |
| `request_id` | uuid | NOT NULL |
| `created_at` | timestamptz | NOT NULL |

İndeksler: `(organization_id, created_at)`, `(actor_user_id, created_at)`, `(entity_type, entity_id, created_at)`, `(request_id)`. Update/delete uygulama rolüne kapatılır. Partitioning, hacim ölçüldükten sonra değerlendirilebilir.

## 4. İlişki ve bütünlük kuralları

- Building, apartment ve tüm alt kaynakların `organization_id` değerleri üst kaynakla aynı olmalıdır.
- Tenant içi FK güvenliği için uygun tablolarda `(organization_id, id)` unique anahtarları ve birleşik FK'ler tercih edilir.
- Domain global hostname benzersizliği organization'lar arası çakışmayı önler.
- Bir primary domain yalnızca `status=active`, SSL-ready ve aktifken seçilebilir; geçişler tanımlı state machine üzerinden olur.
- Finansal ters kayıt aynı organization, building ve apartment kapsamında olmalıdır.
- Payment allocation aynı organization, building, apartment ve currency kapsamında olmalı; toplamlar payment ve charge sınırlarını aşmamalıdır.
- Expense ile bank transaction eşleştirmesi aynı organization ve building içinde ve MVP'de bire bir olmalıdır.
- Document'in expense/building bağlantıları aynı organization'a ait olmalıdır.
- Announcement read kullanıcısı ilan binasına erişebilen aktif resident olmalıdır.

## 5. Silme ve saklama

- Organization kapatılır/suspend edilir; hemen fiziksel silinmez.
- Membership sona erdirilir/revoke edilir; apartment membership geçmişi fiziksel silinmez ve yalnız aktif dönem erişim verir.
- Building/apartment pasifleştirilir.
- Ledger ve audit fiziksel silinmez.
- Bank transaction ve expense için iptal/arşiv yaklaşımı kullanılır.
- Belgeler MVP'de otomatik silinmez; ileride yapılandırılabilir retention ve onaylı hukuki/sözleşmesel politika uygulanır.
- Kişisel veri silme/anonimleştirme ile finansal/yasal saklama yükümlülükleri hukuk danışmanlığıyla netleştirilmelidir.

## 6. Varsayımlar

- UUID üretimi uygulama/veritabanı standardıyla tek biçimde yapılır.
- MVP yalnızca TRY işlemi açar; şema gelecekte para birimini açıkça taşır.
- Daire bakiyesi ayrı doğruluk kaynağı olarak saklanmaz.
- Announcement tek binayı hedefler; çoklu bina yayınında her bina için kayıt üretilebilir.

## 7. Kodlamadan önce kalan kararlar

- Toplu tahakkuk çalıştırmasının batch metadata/audit gereksinimi ve ayrı `assessment_batch` tablosu
- Duyurunun organization genelinde tek kayıtla çoklu binaya gönderilmesi
- Paket ve kullanım için ayrı subscription/usage tablolarının ürün kapsamı
- İlk production backup retention değerleri

## 8. Riskler

- Yalnız uygulama koduyla korunan tenant tutarlılığı insan hatasına açıktır; birleşik FK'ler önemlidir.
- Çok sayıda geniş `jsonb` audit kaydı büyüme ve kişisel veri riski doğurur.
- Gereğinden fazla indeks yazma maliyetini artırabilir; üretim sorguları ölçülmelidir.
- Branding-document FK döngüsü migration planını karmaşıklaştırabilir.

## 9. Uygulanan ilk şema notları

İlk migration aşağıdaki dokuz tenant çekirdek tablosunu oluşturur:

`users`, `organizations`, `organization_brandings`, `organization_domains`,
`organization_memberships`, `buildings`, `building_memberships`, `apartments`,
`apartment_memberships`.

Uygulanan şema, bu belgedeki uzun vadeli tasarımın finansal olmayan ilk
kesitidir. Kullanıcı adı `first_name` ve `last_name` olarak ayrılmıştır.
Membership zamanları `starts_at`/`ends_at`, aktiflik ise `is_active` ile
tutulur. Organization başına tek primary domain PostgreSQL ve SQLite partial
unique indexiyle korunur; service kontrolü kullanıcı dostu erken hata sağlar.

Enum alanları taşınabilirlik için `native_enum=False` ve check constraint ile
üretilmiştir. PostgreSQL exclusion constraint kullanılmamıştır; tarihsel
ApartmentMembership çakışması tenant-safe service içinde kontrol edilir.
Production concurrency koşulları büyüdüğünde transaction/locking veya exclusion
constraint yeniden değerlendirilmelidir.
