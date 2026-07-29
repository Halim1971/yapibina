# Yapıbina

Yapıbina; kapsamlı bina yönetim sistemlerini fazla karmaşık bulan küçük ve orta
ölçekli apartmanlar ile yönetim firmaları için geliştirilen sade, güvenilir ve
şeffaf bir white-label SaaS ürünüdür.

Resident deneyimi dört ana işleve odaklanacaktır:

1. Daire ekstresi
2. Bina banka hareketleri
3. Giderler ve belgeleri
4. Duyurular

Her yönetim firması kendi markası ve doğrulanmış alan adıyla aynı uygulamayı
kullanabilecektir. Temel tenant, domain, üyelik, bina ve daire modelleri
hazırdır; finansal işlevler henüz bulunmamaktadır.

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
- Varsayılan Yapıbina tema değişkenleri
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
  models/           Tenant çekirdeğinin SQLAlchemy 2.x modelleri
  repositories/     İleride eklenecek tenant-scoped veri erişimi
  services/         Tenant-safe ilişki ve doğrulama servisleri
  tenant/           Host normalizasyonu ve gerçek domain lookup
  templates/        Ortak Jinja tabanı ve hata sayfaları
  static/           Varsayılan sade CSS ve JavaScript
config/             Ortam yapılandırmaları
docs/               Onaylanmış mimari belgeler
instance/           Git dışı yerel runtime verileri
scripts/            İleride eklenecek operasyon yardımcıları
tests/              Unit, integration ve functional testler
migrations/         Alembic migration ortamı ve ilk tenant şeması
```

## Henüz bulunmayan özellikler

Bu aşamada banka hareketi, gider, belge, duyuru, audit, notification ve
subscription modelleri yoktur. Kayıt, parola
sıfırlama, e-posta daveti/doğrulaması, MFA, resident gider/duyuru ekranları,
online ödeme,
dosya yükleme, import, production PostgreSQL veritabanı, Nginx, systemd,
Docker ve background job altyapısı oluşturulmamıştır.

Mimari kararlar `docs/` ve `PROJECT_DECISIONS.md` içinde tutulur.
