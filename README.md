# Yapıbina

Yapıbina, Apsiyon'un yerine geçen bir operasyon veya muhasebe sistemi değildir.
Apsiyon ana veri kaynağı olarak kalırken Yapıbina doğrulanmış veriyi
sadeleştiren ve yönetim firmasının markası altında modern ekranlarla sunan
white-label bir read-model platformudur.

Resident deneyimi dört ana işleve odaklanacaktır:

1. Daire ekstresi
2. Bina banka hareketleri
3. Giderler ve belgeleri
4. Duyurular

Her yönetim firması kendi markası ve doğrulanmış alan adıyla aynı uygulamayı
kullanabilecektir. Temel tenant, domain, üyelik, bina ve daire modelleri
ile aidat/ödeme read-model ekranları hazırdır.

Planlanan veri akışı Apsiyon raporları → Apsiyon adapter → Yapıbina standart
ara veri formatı → Yapıbina importer → yönetim/resident ekranlarıdır. Kaynak
rapor kolonları uygulama modeline doğrudan bağlanmaz.

## Mevcut durum

Bu sürüm profesyonel Flask temeli ve tenant çekirdek veri modelini içerir:

- Application factory
- Development, testing ve production yapılandırmaları
- SQLAlchemy, Flask-Migrate ve Flask-Login extension nesneleri
- Blueprint sınırları
- JSON `/health` endpoint'i
- Merkezi 404, 421 ve 500 hata yönetimi
- Aktif OrganizationDomain sorgusuna bağlı güvenli tenant resolution
- User, Organization, Branding, Domain, Building ve Apartment modelleri
- Organization, building ve apartment membership modelleri
- Cross-tenant ilişkiyi reddeden temel service katmanı
- İlk Alembic migration'ı
- Domain ve membership uyumunu doğrulayan güvenli login/logout
- CSRF koruması ve host-scope session/remember cookie ayarları
- IP başına yapılandırılabilir login rate limit
- Kaynak kapsamlı authorization decorator'ları
- Platform organization, branding, domain ve admin atama ekranları
- Tenant-scoped bina, daire, kullanıcı ve üyelik yönetimi
- Organization, building ve user listelerinde sayfalama ve kapsamlı arama
- Decimal tabanlı ChargeBatch, Charge, Payment ve PaymentAllocation çekirdeği
- Tenant-scoped aidat posting, ödeme mahsup, bakiye ve reversal servisleri
- Tenant hostname’e göre marka adı, logo, renk ve destek bilgisi sağlayan
  white-label branding temeli
- Organization admin için organization veya aktif bina hedefli taslak,
  planlı yayın ve arşiv yaşam döngüsüne sahip duyuru yönetimi
- Resident için aktif daire üyeliklerine göre tenant-safe, salt-okunur duyuru
  listesi ve detay görünümü
- Announcement + kullanıcı bazlı AnnouncementRead verisinden türetilen
  uygulama içi bildirim merkezi, okunmamış navbar rozeti ve organization
  aggregate okunma özeti
- Pytest, Ruff ve mypy yapılandırması

## Gereksinimler

- Tercihen Python 3.12; proje Python 3.10 ve üzerini destekler
- Python `venv` ve `pip`
- Production aşamasında PostgreSQL

Bu iskelet yerel doğrulamada Python 3.10.12 ile test edilmiştir.

## Development kurulumu

```bash
cd /home/halim/Documents/YAPIBINA
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Environment dosyasını hazırlayın:

```bash
cp .env.example .env
```

`.env` içindeki development değerlerini yerel ortamınıza göre düzenleyin.
Production secret veya gerçek bağlantı bilgilerini repoya eklemeyin.

## Uygulamayı çalıştırma

```bash
source .venv/bin/activate
flask --app wsgi:app run
```

Health kontrolü:

```bash
curl http://127.0.0.1:5000/health
```

Beklenen yanıt:

```json
{"service":"yapibina","status":"ok"}
```

## Veritabanı ve migration

Development varsayılanı yerel SQLite'tır. Production yapılandırması yalnız
PostgreSQL bağlantı adresini kabul eder. Migration çalıştırmak için:

```bash
flask --app wsgi:app db upgrade
```

Yeni bir model değişikliği onaylandıktan sonra migration üretme örneği:

```bash
flask --app wsgi:app db migrate -m "açıklayıcı migration mesajı"
```

Migration production'a uygulanmadan önce PostgreSQL üzerinde ayrıca
incelenmeli ve staging ortamında denenmelidir.

## Aidat ve ödeme

Finansal temel ve organization admin için sade aidat takip ekranı bulunur:

- `ChargeBatch`, bir binanın belirli dönem aidatlarını aktif dairelere atomik
  olarak post eder.
- `Charge`, dairenin borcunu; `Payment`, alınan ödemeyi temsil eder.
- `PaymentAllocation`, bir ödemeyi aynı dairedeki bir veya daha fazla borca
  mahsup eder. Otomatik mahsup en eski vadeden başlar.
- Fazla ödeme allocation yapılmadan kredi niteliğinde bakiye olarak kalabilir.
- Para değerleri `Numeric(14, 2)` ve Python `Decimal` kullanır.
- Posted finansal kayıtlar silinmez veya temel tutarları değiştirilmez; hatalar
  reversal ile kapatılır.

Bu yapı genel muhasebe veya çift taraflı ledger değildir.

Organization admin, tenant hostname üzerinde `/organization/dues` adresinden
aktif binayı ve dönemi seçebilir; tüm aktif dairelere eşit tutarlı aidat
oluşturabilir, dönem tahakkuk/tahsilat/kalan özetini görebilir ve daireye ödeme
girebilir. Otomatik mahsup en eski açık borçtan başlar. Bu nedenle ekranda
seçili dönemin tahsilatı, yalnız o dönemin borçlarına gerçekten dağıtılmış
ödeme tutarıdır; girilen ödemenin tamamı seçili aya yansımayabilir.

Arayüzde teknik model adları yerine aidat, borç, ödeme ve kalan dili kullanılır.

## Resident finans görünümü

Resident, tenant hostname üzerinde yalnız aktif organization üyeliği ve aktif
ApartmentMembership ile bağlı olduğu aktif daireleri görebilir. `/resident/`
ekranı güncel borcu, son ödemeleri, son hesap hareketlerini ve varsa henüz bir
borca uygulanmamış ödeme tutarını gösterir. Birden fazla daire bağlantısı varsa
yalnız izinli dairelerden seçim yapılabilir.

Resident ekranları salt okunurdur. Hesap ekstresinde teknik ödeme dağıtım
satırları gösterilmez; ödeme yalnız borçlara uygulanan kısmı kadar running
balance değerini azaltır. Kullanılmamış ödeme güncel borçtan otomatik düşülmez.

## Kalite kontrolleri

```bash
pytest
ruff check .
mypy
```

## Demo veri paketi

`demo_data/`, 1 Şubat–31 Temmuz 2026 dönemine ait beş kurgusal site, 50
bağımsız bölüm ve 50 resident içeren standart Excel veri paketidir. Kontrollü
borç/ödeme senaryolarına ek olarak gider ve duyuru veri kümeleri içerir.

```bash
python scripts/generate_demo_data.py
python scripts/validate_demo_data.py
```

Üretim sabit seed ile byte düzeyinde deterministiktir. `manifest.json` her Excel
dosyasının satır sayısını ve SHA-256 değerini taşır. Veriler tamamen kurgusaldır;
e-postalar yalnız `example.com`, telefonlar yalnız `DEMO-` biçimindedir.
Standart paket, önceden oluşturulmuş bir organization'a doğrulama amaçlı veya
kalıcı olarak aktarılabilir:

```bash
flask import-standard-data --organization-id <UUID> --path demo_data --dry-run
flask import-standard-data --organization-id <UUID> --path demo_data
```

Importer manifest/hash/schema doğrulaması yapar; site, daire, resident, borç ve
ödemeleri stabil kaynak anahtarlarıyla idempotent olarak eşler. Gider ve duyuru
satırları doğrulanıp raporlanır, fakat henüz veritabanına yazılmaz. Gerçek
Apsiyon adapter'ı ve tarayıcı otomasyonu oluşturulmamıştır.

Organization admin, tenant panelindeki `/organization/imports` ekranından
canonical ZIP paketini yükleyebilir. Sistem önce salt ön kontrol/dry-run sonucu
gösterir; gerçek aktarım yalnız açık **İçe Aktar** onayından sonra aynı
fingerprint'e sahip geçici paketle başlar. Paketler repository dışında güvenli
geçici alanda tutulur ve onay, vazgeçme veya hata sonrasında temizlenir.

## Organization genel bakışı

Organization admin giriş sonrasında `/organization/` veya
`/organization/dashboard` üzerinde tenant-scoped operasyon özetini görür:
bina/daire/aktif resident sayıları, güncel açık borç, içinde bulunulan ayın
tahakkuk ve ödeme toplamları, tahsilat oranı, son başarılı/başarısız import
durumu, ilk 10 bina özeti ve son 10 finansal hareket.

Açık borç yalnız posted charge toplamından posted payment'lara bağlı geçerli
allocation toplamı çıkarılarak hesaplanır ve sıfırın altına düşmez. Aylık ödeme
doğrudan aynı ay tarihli posted payment toplamıdır; allocation nedeniyle ikinci
kez sayılmaz. Aylık tahakkukta önce charge dönem alanları, bunlar yoksa
`due_date` kullanılır. Tüm hesaplar `Decimal` ve açık `organization_id`
kapsamıyla yürütülür.

## Organization bina listesi

Organization admin `/organization/buildings` ekranında yalnız aktif tenant
kapsamındaki binaları görür. Liste; ad ve adres araması, izin verilen metriklere
göre sıralama ve 20/50/100 kayıtlık server-side sayfalama sağlar. Her satırda
daire ve aktif resident sayısı, güncel açık borç, içinde bulunulan ayın ödeme
toplamı ve bina durumu gösterilir.

Finansal ve resident metrikleri Genel Bakış ile aynı tanımları kullanır:
açık borç posted charge'lardan geçerli allocation'ların çıkarılmasıyla,
aylık tahsilat ise allocation'lardan bağımsız olarak tekil posted payment
toplamıyla hesaplanır.

## Organization bina detayı

Organization admin bina listesinden tenant-scoped bina detayına geçebilir.
Detay ekranı bina özeti, aylık finans metrikleri, son finansal hareketler ve
daire bazında resident/borç/tahakkuk/tahsilat özetlerini sunar. Daire listesi
resident veya daire bilgisiyle aranabilir; izin verilen metriklerle sıralanır
ve 20/50/100 kayıtlık server-side sayfalama kullanır.

Son ödeme, mevcut modelde doğrudan daireye bağlı en yeni posted `Payment`
kaydıdır. Tahsis edilmemiş ödeme aylık tahsilatta görünür fakat açık borcu
azaltmaz. Finansal metrikler Genel Bakış ve Bina Listesi ile ortak tarih,
dönem ve Decimal kurallarını kullanır. Bu aşamada yeni Building CRUD veya
Apartment CRUD davranışı eklenmemiştir.

## Organization daire detayı

Organization admin bina detayından salt-okunur daire detayına geçebilir. Typed
read-model; daire kimliği, aktif sakinler, finans özeti, tahakkuk ve ödeme
geçmişleri ile bakiye hareketlerini tenant scope içinde üretir. Route ve
template finans hesabı yapmaz.

Açık borç posted charge toplamından yalnız geçerli allocation toplamının
çıkarılmasıdır. Tahsis edilmemiş ödeme açık borcu veya running balance'ı
azaltmaz. Bakiye hareketinde charge borcu artırır; allocation timezone-aware
`created_at` anında borcu azaltır. Charge ve payment listeleri bağımsız arama,
allowlist sıralama ve 20/50/100 kayıtlık server-side pagination kullanır.
Apartment CRUD, ödeme/tahakkuk değiştirme veya JSON API bu kapsamda yoktur.

## White-label marka ayarları

Organization admin `/organization/settings/branding` ekranından kendi tenant’ının
görünen adını, kısa adını, renklerini, destek bilgilerini, footer metnini ve
logosunu yönetebilir. Tenant login, organization ve resident ekranları doğrulanmış
hostname’in effective branding read-model’ini kullanır. Branding kaydı yoksa
organization adı ve güvenli varsayılan palet kullanılır; platform ekranları
Yapıbina temasında kalır.

Logolar instance altındaki public/executable olmayan, organization-scope
`branding_assets` alanında rastgele adla saklanır. Yalnız içeriği Pillow ile
doğrulanmış PNG, JPEG ve WebP kabul edilir; SVG reddedilir. Varsayılan üst sınır
2 MB’dir ve `BRANDING_LOGO_MAX_BYTES` ile değiştirilebilir. Yeni logo ve database
güncellemesi başarılı olmadan eski logo kaldırılmaz.

Branding Yapıbina’ya ait yerel tenant configuration’dır. Standart veri importer’ı
branding oluşturmaz, değiştirmez veya silmez. Gelecekte mobil istemciler de aynı
transport-independent effective branding servisinden yararlanacaktır; bu aşamada
JSON API veya mobil asset manifesti yoktur. DNS ownership, domain provisioning ve
TLS otomasyonu da bu kapsamda değildir.

## Organization resident detayı

Organization admin, daire detayındaki aktif sakinlerden salt-okunur Resident
Detail ekranına geçebilir. Mevcut domainde ayrı Resident tablosu yoktur: sakin
kimliği `User`, tenant bağı `OrganizationMembership`, aktif yerleşimler
`ApartmentMembership` ile temsil edilir. Bir kullanıcı birden fazla aktif
daireye bağlıysa finans görünümü daire bazında ayrı seçilir.

Finans resident'a değil apartment'a aittir. Aynı dairedeki sakinler aynı
“Bağlı Dairenin Finansal Durumu” görünümünü paylaşır; ayrı resident borcu
üretilmez. Bu görünüm Apartment Detail typed read-model servisini composition
ile kullanır ve aynı Decimal, allocation, arama, sıralama ve pagination
kurallarını korur. Building, Apartment ve sakin ana kayıtları normal akışta
importer kaynaklı ve salt okunurdur; manuel CRUD bu kapsamda bulunmaz.

## Kimlik doğrulama

Giriş yalnız kullanıcının yetkili olduğu host üzerinde çalışır:

- Platform hostname yalnız aktif platform super admin hesaplarını kabul eder.
- Tenant hostname aktif User, Organization, Domain ve OrganizationMembership gerektirir.
- Platform super admin tenant hostunda otomatik tenant yetkisi kazanmaz.
- Login ve logout POST işlemleri CSRF korumalıdır.
- Harici ve protocol-relative `next` hedefleri reddedilir.

Login rate limit varsayılan olarak IP başına dakikada 5 ve saatte 30 denemedir.
Mevcut `memory://` storage yalnız tek süreçli development/test için uygundur.
Çok worker production öncesi ortak storage gerekir; Redis bu aşamada kurulmamıştır.

MFA henüz uygulanmamıştır. Platform super admin MFA zorunluluğu production
yayınından önce ayrı bir aşamada tamamlanacaktır.

## Yapı

```text
app/
  blueprints/       HTTP modül sınırları
  imports/          Standart Excel reader, doğrulama ve tenant-safe importer
  models/           Tenant çekirdeğinin SQLAlchemy 2.x modelleri
  repositories/     İleride eklenecek tenant-scoped veri erişimi
  services/         Tenant-safe ilişki ve doğrulama servisleri
  tenant/           Host normalizasyonu ve gerçek domain lookup
  templates/        Ortak Jinja tabanı ve hata sayfaları
  static/           Varsayılan sade CSS ve JavaScript
config/             Ortam yapılandırmaları
docs/               Onaylanmış mimari belgeler
instance/           Git dışı yerel runtime verileri
scripts/            Demo veri üretim ve doğrulama yardımcıları
tests/              Unit, integration ve functional testler
migrations/         Alembic migration ortamı ve ilk tenant şeması
```

## Henüz bulunmayan özellikler

Bu aşamada banka hareketi, gider, belge, duyuru, audit, notification ve
subscription modelleri yoktur. Kayıt, parola
sıfırlama, e-posta daveti/doğrulaması, MFA, resident gider/duyuru ekranları,
online ödeme,
gider/belge yükleme, production PostgreSQL veritabanı, Nginx, systemd,
Docker ve background job altyapısı oluşturulmamıştır. Standart Excel importer
mevcuttur; Apsiyon adapter henüz bulunmaz.

Mimari kararlar `docs/` ve `PROJECT_DECISIONS.md` içinde tutulur.

## Web ve mobil istemci hazırlığı

Yapıbina bugün server-rendered Flask web uygulamasıdır. Gelecekte Android ve
iOS istemcileri aynı domain/application service katmanını kullanacaktır.
Planlanan JSON API `/api/v1` altında sürümlenecek; ancak bu aşamada API
blueprint'i, token authentication veya mobil uygulama oluşturulmamıştır.

Yeni özellik geliştirirken aşağıdaki kontrol listesi uygulanır:

- İş kuralları route, Jinja template, Flask session, flash veya form nesnesine
  gömülmez.
- Service sonuçları HTML'e özel olmaz; typed model/view-model döndürür.
- Kaynak kimliklerinde stabil UUID kullanılır.
- Her tenant sorgusu açık ve doğrulanmış `organization_id` scope'u taşır.
- Web ve gelecekteki API aynı authorization policy/use-case kurallarını
  kullanır.
- Finansal değerler `Decimal` kalır; gelecekte JSON'da decimal string olarak
  taşınır.
- Veritabanı zamanı UTC, dış tarih-saat gösterimi ISO 8601 ve timezone bilgili
  olur.
- Listelemeler tek pagination sözleşmesine uyar.
- “İleride mobil gerekir” gerekçesiyle gereksiz endpoint eklenmez.
- Açıkça istenmedikçe JSON API geliştirilmez.

Announcement kalıcı yönetim içeriğidir ve organization/bina hedefli web
görünümleri uygulanmıştır. `AnnouncementRead`, bir kullanıcının görünür bir
duyuruyu ilk açtığı zamanı apartment’tan bağımsız ve idempotent olarak saklar.
Bildirim merkezi kalıcı bir teslim/fan-out tablosu değil, görünür Announcement
ve AnnouncementRead birleşiminden türetilir. Push ise ayrı ve başarısızlığı ana
işlemi geri almayan teslim altyapısıdır. Push notification, outbox/background
job ve device token yönetimi henüz uygulanmamıştır.
