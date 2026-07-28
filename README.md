# Yapıbina

Yapıbina; kapsamlı bina yönetim sistemlerini fazla karmaşık bulan küçük ve orta
ölçekli apartmanlar ile yönetim firmaları için geliştirilen sade, güvenilir ve
şeffaf bir white-label SaaS ürünüdür.

Resident deneyimi dört ana işleve odaklanacaktır:

1. Daire ekstresi
2. Bina banka hareketleri
3. Giderler ve belgeleri
4. Duyurular

Her yönetim firması ileride kendi markası ve doğrulanmış alan adıyla aynı
uygulamayı kullanabilecektir. Mevcut iskelette yalnız güvenli tenant çözümleme
arayüzü vardır; organization/domain modelleri ve veritabanı sorgusu henüz yoktur.

## Mevcut durum

Bu sürüm yalnız profesyonel Flask proje temelidir:

- Application factory
- Development, testing ve production yapılandırmaları
- SQLAlchemy, Flask-Migrate ve Flask-Login extension nesneleri
- Blueprint sınırları
- JSON `/health` endpoint'i
- Merkezi 404, 421 ve 500 hata yönetimi
- Güvenli tenant-resolution iskeleti
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

## Kalite kontrolleri

```bash
pytest
ruff check .
mypy
```

## Yapı

```text
app/
  blueprints/       HTTP modül sınırları
  models/           İleride eklenecek SQLAlchemy modelleri
  repositories/     İleride eklenecek tenant-scoped veri erişimi
  services/         İleride eklenecek iş kuralları
  tenant/           Host normalizasyonu ve tenant çözümleme arayüzü
  templates/        Ortak Jinja tabanı ve hata sayfaları
  static/           Varsayılan sade CSS ve JavaScript
config/             Ortam yapılandırmaları
docs/               Onaylanmış mimari belgeler
instance/           Git dışı yerel runtime verileri
scripts/            İleride eklenecek operasyon yardımcıları
tests/              Unit, integration ve functional testler
```

## Henüz bulunmayan özellikler

Bu aşamada organization, domain, kullanıcı, bina, daire, tahakkuk, ödeme, banka
hareketi, gider ve duyuru modelleri yoktur. Migration, gerçek login, yönetim veya
resident ekranları, dosya yükleme, import, PostgreSQL veritabanı, Nginx,
systemd, Docker ve background job altyapısı oluşturulmamıştır.

Mimari kararlar `docs/` ve `PROJECT_DECISIONS.md` içinde tutulur.
