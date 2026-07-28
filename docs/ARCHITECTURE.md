# Yapıbina Sistem Mimarisi

## 1. Amaç ve mimari sınır

Yapıbina, küçük ve orta ölçekli apartmanlar ile bina yönetim firmalarına yönelik, white-label ve multi-tenant bir SaaS ürünüdür. Resident deneyimi dört işleve sınırlandırılır: daire ekstresi, bina banka hareketleri, giderler ve duyurular. Mimari; genel muhasebe, bordro, CRM, satın alma veya ERP işlevlerine doğru genişlemeyi varsaymaz.

Temel kalite hedefleri:

- Tenant verisinin her katmanda izolasyonu
- Finansal hareketlerde izlenebilirlik ve geri alınabilirlik
- Sade kullanıcı deneyimi
- Müşteri alan adı ve markasıyla çalışma
- Ubuntu VPS üzerinde güvenli, taşınabilir işletim
- Test edilebilir, modüler ve uzun ömürlü kod tabanı

## 2. Genel sistem görünümü

```text
Kullanıcı
  -> HTTPS / müşteri hostname'i
  -> Nginx (TLS, yönlendirme, statik içerik, boyut sınırı)
  -> Gunicorn (WSGI süreçleri)
  -> Flask application factory
       -> güvenilir host kontrolü ve tenant resolution
       -> kimlik doğrulama ve yetkilendirme
       -> blueprint/controller
       -> service/use-case
       -> repository/query
       -> SQLAlchemy
  -> PostgreSQL

Flask -> Storage adapter -> yerel özel depolama / ileride S3 uyumlu obje depolama
Flask -> Notification provider -> ilk aşamada uygulama içi / ileride Web Push
Flask -> Bank import/provider adapters -> MVP'de CSV/Excel, ileride banka API'leri
```

Tek PostgreSQL veritabanı ve ortak schema kullanılır. `organization` tenant sınırıdır. Tenant kapsamındaki kayıtlar `organization_id` taşır; yalnızca dolaylı ilişkiye güvenilmez.

## 3. Önerilen proje yapısı

Bu yapı sonraki uygulama aşaması için öneridir; bu belge oluşturulurken klasörlerin hiçbiri oluşturulmamıştır.

```text
app/
  __init__.py                 # create_app
  extensions.py               # uzantı nesneleri
  config/                     # çalışma ortamı ayar sınıfları
  tenancy/                    # host çözümleme ve tenant context
  auth/                       # kimlik doğrulama ve policy yardımcıları
  models/                     # SQLAlchemy modelleri
  repositories/              # tenant-sınırlı veri erişimi
  services/                  # iş kuralları / use-case'ler
  blueprints/
    platform/
    organization/
    building/
    resident/
    auth/
  storage/                    # storage portu ve adapter'ları
  banking/                    # import ve banka provider portları
  notifications/             # bildirim portları
  audit/
  templates/
  static/
  utils/
migrations/
tests/
  unit/
  integration/
  functional/
  security/
config/
scripts/
docs/
instance/
```

`utils/` yalnızca genel, durumsuz yardımcılar içindir; iş kuralları buraya taşınmamalıdır.

## 4. Katmanlar ve bağımlılık yönü

### HTTP / blueprint katmanı

İstek verisini doğrular, aktif kullanıcı ve tenant context'i kullanır, service çağırır ve yanıt üretir. İş kuralı veya serbest SQL içermez.

### Service / use-case katmanı

Tahakkuk ekleme, ödeme kaydetme, gider-belge ilişkilendirme, domain aktifleştirme gibi işlemlerin iş kurallarını ve transaction sınırlarını yönetir. Yetki kapsamını açıkça alır; tenant bilgisini istemciden gelen form alanından kabul etmez.

### Repository / query katmanı

Veri erişimini merkezileştirir. Tenant kapsamındaki her okuma ve yazma aktif `organization_id` ile sınırlanır. Ayrıntılı listeleme ve raporlama için ayrı query nesneleri kullanılabilir. Bir kaydı yalnızca global ID ile getiren genel amaçlı metotlar tenant alanında yasaktır.

### Model katmanı

İlişkileri, veritabanı constraint'lerini ve temel veri bütünlüğünü tanımlar. Yetkilendirmenin tek kaynağı değildir; service ve repository kontrolleri devam eder.

### Altyapı adapter'ları

Dosya depolama, bildirim, banka içe aktarma ve gelecekteki dış servisler port/adapter yaklaşımıyla soyutlanır. İş mantığı yerel dosya yolu, belirli banka veya S3 SDK'sına bağlanmaz.

## 5. Flask application factory

`create_app(config_name=None)` yaklaşımı kullanılmalıdır. Factory:

1. Doğrulanmış environment yapılandırmasını yükler.
2. SQLAlchemy, migration, login, CSRF ve diğer uzantıları başlatır.
3. Blueprint'leri kaydeder.
4. Host doğrulama ve tenant resolution kancalarını kaydeder.
5. Hata işleyicileri, request ID ve yapılandırılmış loglamayı kurar.
6. Health endpoint'lerini uygulama bağımlılıklarıyla ilişkilendirir.

Factory; testlerde izole uygulama örnekleri, farklı konfigürasyonlar ve platform bağımsız çalışma sağlar. Import anında veritabanı bağlantısı veya dış servis çağrısı yapılmamalıdır.

## 6. Blueprint yapısı

- `auth`: giriş, çıkış, parola işlemleri
- `platform`: yalnızca `platform_super_admin`
- `organization`: organization ayarları, marka, kullanıcı ve bina yönetimi
- `building`: building manager operasyonları
- `resident`: dört ana resident görünümü

Rol tek başına yeterli değildir. Her route ayrıca organization üyeliğini, bina atamasını veya daire üyeliğini doğrular. Platform yönetim alanı müşteri hostlarından ayrılmalı ve yalnızca merkezi, açıkça izin verilen platform hostunda sunulmalıdır.

## 7. Tenant resolution ve tenant context

Her istek için sıralama:

1. Host normalize edilir: port kaldırılır, küçük harfe çevrilir, IDNA kuralları uygulanır.
2. Host yalnızca uygulama yapılandırmasındaki platform hostları veya aktif ve doğrulanmış `organization_domain.hostname` kayıtları arasında aranır.
3. Eşleşen aktif organization yüklenir.
4. Request-scope, değiştirilemez bir tenant context oluşturulur.
5. Oturum açmış kullanıcının bu organization ile geçerli ilişkisi kontrol edilir.
6. Repository ve service işlemleri context'teki `organization_id` ile çalışır.

`X-Forwarded-Host` yalnızca güvenilen Nginx proxy zincirinden ve doğru ProxyFix ayarıyla kabul edilir. İstemciden gelen `organization_id` tenant seçmek için kullanılmaz. Bilinmeyen host güvenli bir hata sayfasıyla reddedilir; otomatik yönlendirme yapılacaksa yalnızca sabit merkezi URL'ye yapılır.

Background job'lar HTTP context'e dayanamaz; tenant kimliğini iş yükünde açıkça ve doğrulanmış biçimde taşımalıdır.

## 8. Kimlik doğrulama ve yetkilendirme

Flask-Login oturum yönetimini sağlar. Yetkilendirme policy tabanlıdır:

- Platform rolü platform kapsamındadır.
- Organization rolü membership üzerinden değerlendirilir.
- Building manager için aktif `building_membership` aranır.
- Resident için aktif `apartment_membership` ve hedef binayla ilişki aranır.

Bir kullanıcı birden fazla organization, bina ve daireyle ilişkili olabilir. Roller kullanıcı tablosunda global tek alan olarak tutulmaz. Resident yalnız `status=active` apartment membership bulunan daireyi ve onun binasını görebilir; sona ermiş/pasif üyelik geçmiş veriye otomatik erişim sağlamaz. Organization admin veya yetkili building manager üyeliği aktif/pasif yapabilir, fakat üyelik geçmişi fiziksel silinmez. Yetki reddi varsayılan davranıştır. IDOR koruması için hedef kayıt; ID, aktif organization ve gerekli bina/daire kapsamıyla birlikte sorgulanır.

## 9. Finansal ledger

Basit ve güvenilir bir hareket defteri yaklaşımı kullanılır. Finansal kavramlar açıkça ayrılır:

- Her hareket bir daire, bina ve organization kapsamındadır.
- Tahakkuk/borç türü `aidat`, `ek_borc`, `duzeltme` veya `diger` olur; her borcun `due_date`, isteğe bağlı `period_year` ve `period_month` alanları vardır.
- Tahakkuklar MVP'de yönetici tarafından manuel veya toplu oluşturulur; otomatik tekrarlayan aidat ve gecikme faizi/cezası MVP dışıdır.
- Ödeme ayrı bir append-only finansal kayıttır ve bir veya daha fazla açık borca `payment_allocation` kayıtlarıyla dağıtılır.
- Kısmi ödeme desteklenir. Varsayılan otomatik dağıtım en eski vadesi geçmiş, sonra en eski açık borçtan başlar.
- Ödeme tutarı ile allocation toplamı service ve veritabanı seviyesinde kontrol edilir. Kalan dağıtılmamış tutar daire kredi/alacak bakiyesi olarak korunur.
- Hatalı kesinleşmiş hareket güncellenmez veya fiziksel silinmez; ters kayıt oluşturulur.
- Ters kayıt, orijinal kayda `reversal_of_id` ile bağlanır.
- Tutar `Numeric` / `Decimal` olarak, pozitif mutlak değer ve ayrı yön bilgisiyle tutulur.
- Bakiye, ledger toplamından hesaplanan asıl veridir; performans için özet tutulursa yeniden üretilebilir cache kabul edilir.

Allocation toplamı gibi tablolar arası kurallar transaction içinde service doğrulaması ve PostgreSQL deferred constraint trigger ile korunmalıdır. Ödeme ters çevrildiğinde allocation etkileri aynı transaction'da geçersizleştirilir. Çift taraflı genel muhasebe MVP kapsamı değildir. İdempotency anahtarı, transaction, benzersiz ters kayıt kısıtı ve audit ile mükerrer/hatalı kayıt riski azaltılır.

## 10. White-label tema

Marka çözümleme merkezi bir `BrandingService` üzerinden yapılır. Öncelik:

1. Aktif organization branding değeri
2. Yapıbina varsayılanı

Varsayılan palet:

```text
--color-primary: #0f3f3f
--color-secondary: #d4d9d5
--color-surface: #f4f4f4
--color-white: #ffffff
```

Renk değerleri güvenli biçimde doğrulanır ve yalnızca izin verilen CSS custom property değerleri olarak üretilir. Her müşteri için ayrı template veya CSS kopyası oluşturulmaz. Logo ve favicon, organization kapsamlı document kayıtları üzerinden servis edilir.

## 11. Dosya storage yaklaşımı

`StorageService` portu en az `put`, `open`, `delete/archive`, `exists` ve güvenli indirme URL/stream işlemlerini tanımlar. MVP adapter'ı uygulamanın public static dizini dışında özel yerel depolama kullanır. İleride S3 uyumlu adapter aynı portu uygular.

MVP'de yalnız PDF, JPG, JPEG ve PNG; dosya başına en fazla 10 MB kabul edilir. Depolama anahtarı tahmin edilemez olmalı; organization kapsamını içerebilir fakat kullanıcı dosya adı doğrudan yol olarak kullanılmamalıdır. Metadata veritabanında tutulur. İndirme yetkili Flask endpoint'inden geçer; organization ve ilişkili entity kapsamı tekrar doğrulanır. MIME ve uzantı birlikte kontrol edilir. Malware taraması için adapter/hook bulunur fakat harici antivirüs MVP'de zorunlu değildir. Otomatik silme yapılmaz; retention daha sonra hukuki ve sözleşmesel ihtiyaca göre yapılandırılır.

## 12. Banka adapter yaklaşımı

MVP:

- Manuel hareket girişi
- Kontrollü CSV/Excel import pipeline'ı
- Önizleme, kolon eşleme, doğrulama, idempotency ve sonuç raporu

`BankTransactionImporter` ortak bir normalize edilmiş kayıt üretir. Dosya formatına veya bankaya özel parser'lar adapter'dır. Gelecekte `BankProvider` portu kimlik doğrulama, hesap listeleme ve hareket senkronizasyonu işlevlerini sağlayabilir. Dış banka kaydı için provider + external ID benzersizliği mükerrerliği engeller. MVP'de banka hareketi–gider eşleştirmesi isteğe bağlı, manuel ve bire birdir; iki tarafta da partial unique constraint uygulanır. Kısmi, bölünmüş veya çoklu mutabakat sonraya bırakılır.

## 13. Bildirim mimarisi

MVP'de duyuru uygulama içinde gösterilir ve okunma bilgisi saklanır. Duyuru yayınlama service'i, ileride bir `NotificationDispatcher` portuna domain olayı verebilir. Web Push, e-posta veya başka kanal adapter'ları daha sonra eklenir. Bildirim teslim durumu duyurunun yayınlanmış olmasının doğruluk kaynağı değildir; tekrar deneme ve idempotency ayrı ele alınır.

## 14. Audit yaklaşımı

Kritik değişiklikler aynı veritabanı transaction'ında append-only audit kaydı üretir. Audit; actor, tenant, eylem, entity, önceki/sonraki güvenli alanlar, IP, user-agent ve request ID içerir. Parola özeti, token, session ve secret değerleri audit'e yazılmaz.

Normal uygulama rolleri audit kayıtlarını güncelleyemez veya silemez. Uygulama servislerinde audit yazmayı unutma riskine karşı kritik use-case'ler ortak bir audit writer kullanır. Yüksek güvence gerektiğinde PostgreSQL izinleri veya tetikleyici tabanlı ek koruma yeniden değerlendirilebilir.

## 15. Güvenlik

- Host allowlist ve doğrulanmış domain çözümleme
- Her sorguda tenant ve kaynak kapsamı
- CSRF koruması, güvenli cookie'ler, session yenileme
- Çıktı kaçışlama ve sınırlı zengin metin
- Parametreli SQLAlchemy sorguları
- Parola hash'i için güncel adaptif algoritma
- Giriş ve hassas işlemlerde rate limiting
- Dosya yükleme doğrulaması ve private storage
- En az yetkili veritabanı ve işletim sistemi hesapları
- Secret'ların koddan ve Git'ten ayrılması
- Yapılandırılmış, kişisel/veri hassasiyetine dikkat eden loglar

Ayrıntılar `SECURITY_AND_OPERATIONS.md` içindedir.

## 16. Production mimarisi

Nginx 80/443 bağlantılarını karşılar, HTTP'yi HTTPS'ye yönlendirir, doğru hostu koruyarak Unix socket veya loopback üzerindeki Gunicorn'a iletir. Statik varlıkları sunabilir; kullanıcı yüklemelerini doğrudan public dizinden sunmaz. İstek ve yükleme boyutu limitlerini uygular.

Gunicorn systemd tarafından yönetilir; worker sayısı ölçümle belirlenir. Flask tenant çözümleme, yetki ve uygulama işlemlerini yürütür. PostgreSQL yalnızca gerekli yerel/özel ağ erişimine açılır. Uygulama ve migration için yetkiler ayrıştırılabilir.

Operasyonel gereksinimler:

- Günlük şifreli PostgreSQL yedeği ve düzenli geri yükleme testi
- Belgelerin günlük, ayrı ve sürümlü yedeği
- Yalnız VPS'de tutulmayan en az bir şifreli off-site kopya
- Başlangıç RPO 24 saat, RTO 4 saat; retention environment/configuration ile yönetilir
- Log rotation ve merkezi hata takibi
- Liveness ve dependency-aware readiness kontrolleri
- Development/staging/production ayırımı
- systemd environment veya uygun secret store ile secret yönetimi
- Sürümlemeli dağıtım, migration öncesi yedek ve geri alma prosedürü

## 17. Varsayımlar

- İlk sürüm tek ülke, TRY ve Türkçe kullanımına odaklanır.
- Veritabanında zamanlar UTC, arayüzde `Europe/Istanbul` kullanılır.
- Bir bina tam olarak bir organization'a bağlıdır.
- Bir daire aynı anda tek binaya bağlıdır.
- Resident yalnızca aktif membership bulunan dairelerin ve onların binalarının görünür verisini okur; sona eren ilişki geçmiş erişim sağlamaz.
- Finansal kayıt para birimi MVP'de TRY olsa da alan düzeyinde `currency_code` tutulur.

## 18. Kodlamadan önce kalan kararlar

- Excel desteği için kabul edilecek kesin formatlar
- Platform yönetim hostunun kesin adı
- Bilinmeyen hostun 404/421 ile reddi mi, merkezi sayfaya yönlendirilmesi mi
- Toplu tahakkuk işleminde kullanılacak kesin seçim/önizleme ve idempotency kuralları
- İlk production backup retention gün/hafta/ay değerleri

## 19. Başlıca riskler

- Tenant filtresinin tek bir sorguda unutulması veri sızıntısına yol açabilir.
- Domain doğrulaması ile DNS/SSL aktivasyonu arasında yarış koşulları oluşabilir.
- Finansal kayıtların sonradan değiştirilmesi güven kaybı yaratabilir.
- Yerel storage yedeğinin veritabanı yedeğiyle tutarsız olması geri yüklemeyi zorlaştırabilir.
- CSV/Excel verisi formül, encoding, tarih ve ondalık biçimi açısından güvenilmezdir.
- White-label özelleştirmesinin sınırsızlaşması bakım maliyetini artırabilir.
