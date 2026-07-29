# Standart Excel Importer

## Sınır ve veri akışı

Apsiyon ana operasyon ve veri kaynağıdır. Importer Apsiyon ekranına bağlanmaz;
yalnız adapter-bağımsız Yapıbina standart Excel paketini okur:

`Apsiyon raporları → gelecekteki adapter → standart Excel → importer → Yapıbina`

Apsiyon adapter, scraping, banka entegrasyonu, gider ve duyuru UI bu kapsamda
yoktur. Expense ve announcement dosyaları doğrulanır ve ImportRun sayaçlarında
`deferred` olarak raporlanır; persist edilmez.

## Doğrulama

Reader manifesti, desteklenen schema sürümünü, beklenen dosya/kolonları,
SHA-256 değerlerini, foreign key ilişkilerini, enum/status değerlerini, TRY
para birimini ve Decimal tutarları doğrular. Kaynak dosyalarına güvenilmez.

## Idempotency ve kaynak anahtarları

`ExternalRecordMap`, `(organization_id, source_system, entity_type,
source_key)` birleşimini benzersiz tutar. Böylece farklı tenant veya source
system aynı source key'i güvenle kullanabilir. Site `Building`, unit
`Apartment`, resident global `User` ve tenant üyelikleriyle eşlenir.

Package fingerprint schema sürümü ile manifestteki sıralı dosya/hash
değerlerinden üretilir. Daha önce tamamlanan aynı fingerprint no-op olur ve
`already_imported` sonucu döner.

Merkezi mapping'in `internal_id` alanı polymorphic UUID olduğundan database
foreign key'i taşımaz. Entity türü ve tenant bütünlüğü importer service içinde
her erişimde doğrulanır; bu bilinen bir risktir.

## Güncelleme ve silme politikası

Site adı/adresi, resident adı/telefonu ve finansal açıklama gibi güvenli alanlar
güncellenebilir. Charge/payment tutarı, dairesi, binası, tarihi ve ödeme yöntemi
gibi bakiye kimliğini değiştiren alanlar reddedilir ve import rollback edilir.

Paket dışında kalan kayıtlar silinmez veya pasifleştirilmez. Snapshot ve hareket
listesi semantiği, gerçek kaynak raporları incelendikten sonra ayrıca
kararlaştırılacaktır.

Imported charge kayıtları posted ve `charge_batch_id=null` oluşturulur. Standart
sözleşmede stabil charge anahtarı varken yapay batch üretmek, yönetici batch
akışının anlamını bozacağı için tercih edilmemiştir. Ödemeler mevcut
oldest-debt-first allocation servisini kullanır; fazla tutar dağıtılmamış kalır.

## Transaction ve eşzamanlılık

ImportRun önce `running` olarak kalıcılaştırılır. Domain değişiklikleri tek
transaction içinde uygulanır; hata halinde tamamı rollback edilir ve run
`failed` olarak güncellenir. Organization satırı PostgreSQL'de `FOR UPDATE`
kilitlenir. Ayrıca organization başına tek `running` run partial unique index
ile korunur. SQLite testleri unique guard'ı doğrular; gerçek satır kilitleme
davranışı production PostgreSQL entegrasyon testinde ayrıca izlenmelidir.

## CLI

```bash
flask import-standard-data \
  --organization-id <UUID> \
  --path demo_data \
  --dry-run

flask import-standard-data \
  --organization-id <UUID> \
  --path demo_data
```

`--source-system` varsayılanı `standard_excel` değeridir.
`--created-by-user-id` isteğe bağlıdır. Dry-run dosyaları ve planlanan
insert/update/skip sayılarını doğrular; kalıcı ImportRun veya domain değişikliği
bırakmaz.

## Bilinen riskler

- E-posta global benzersizdir; aynı e-posta varsa global User yeniden kullanılır
  ancak tenant membership ayrı oluşturulur.
- Harici mapping UUID'si polymorphic olduğundan DB seviyesinde entity FK yoktur.
- Çok uzun importlar senkron CLI transaction süresini artırabilir.
- Gider/duyuru persistence, gerçek adapter ve silme semantiği sonraki aşamadadır.
