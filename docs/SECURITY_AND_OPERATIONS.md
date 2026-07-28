# Güvenlik ve Operasyon Mimarisi

## 1. Güvenlik hedefleri

Öncelik sırası:

1. Organization'lar arası veri sızıntısını önlemek
2. Finansal ve audit kayıtlarının bütünlüğünü korumak
3. Hesap, session ve dosya erişimini korumak
4. Güvenli ve geri alınabilir production işletimi

Güvenlik yalnız route decorator'larına bırakılmaz; Nginx, Flask request lifecycle, policy, service, repository, PostgreSQL constraint/izinleri ve storage katmanlarında uygulanır.

## 2. Kimlik doğrulama

- Flask-Login server-side session kimliği için kullanılır.
- Kullanıcı global kimliktir; organization erişimi aktif membership ile belirlenir.
- Tenant hostunda giriş, yalnız o tenant'ta aktif ilişkisi olan kullanıcı için başarılıdır.
- Başarısız mesajlar e-posta veya başka tenant üyeliği hakkında bilgi vermez.
- Başarılı girişte session ID yenilenir; privilege değişiminde mevcut session'lar geçersizleştirilebilir.
- Parola sıfırlama token'ı yüksek entropili, tek kullanımlık, süreli ve kullanıcı/parola sürümüne bağlıdır.
- `platform_super_admin` için MFA ilk production yayınından önce zorunludur.
- `organization_admin` için MFA desteği mimaride planlanır ve sonraki bir aşamada zorunlu yapılabilir; henüz uygulanmamıştır.
- `building_manager` ve `resident` için MFA MVP'de zorunlu değildir.
- Platform destek erişimi normal/sınırsız tenant erişimi sağlamaz. Gerektiğinde süreli, gerekçeli, açıkça yetkilendirilmiş ve eksiksiz audit edilen break-glass oturumu kullanılır.
- Destek veya yönetici hiçbir koşulda kullanıcının parolasını göremez/öğrenemez.

## 3. Parola güvenliği

- Güncel adaptif hash: Argon2id tercih edilir; mevcut ekosistem gerekçesiyle bcrypt/scrypt alternatif olabilir.
- Uygun maliyet parametresi production donanımında ölçülür.
- Ham parola hiçbir zaman log, audit veya veritabanına yazılmaz.
- Uzun parola/passphrase desteklenir; makul maksimumla DoS önlenir.
- Bilinen sızdırılmış parola kontrolü, güvenli entegrasyon mümkünse değerlendirilir.
- Zorunlu periyodik değiştirme yerine olay/risk bazlı değiştirme uygulanır.
- Platform admin MFA, production yayını öncesindeki ayrı bir teslimatta zorunlu kılınacaktır; organization admin için desteklenen ve zorunlu kılınabilir policy de henüz uygulanmamıştır.

## 4. Session ve cookie

Production:

- `Secure=true`
- `HttpOnly=true`
- `SameSite=Lax` varsayılan; akış gerektirirse kontrollü değişiklik
- Host-only cookie; geniş `.yapibina.com` domain cookie yok
- Tahmin edilemez secret key ve düzenli kontrollü rotation
- Mutlak ve idle timeout
- Girişte ve privilege değişiminde session yenileme

Özel domainler farklı origin olduğundan session paylaşılmaz. Domain değişikliğinde yeniden giriş kabul edilen güvenli davranıştır.

## 5. CSRF

Tüm state-changing form ve endpoint'lerde CSRF token zorunludur. `GET` durum değiştirmez. HTMX/JavaScript kullanılırsa token güvenli header/form mekanizmasıyla iletilir. Login CSRF ve logout CSRF de korunur. Webhook gibi gelecekteki istisnalar ayrı imza doğrulamasıyla dar kapsamlı tutulur.

## 6. XSS ve içerik güvenliği

- Jinja autoescape kapatılmaz.
- Duyuru içeriği başlangıçta düz metin tercih eder.
- Zengin metin gerekirse server-side allowlist sanitizer kullanılır.
- Marka metni, dosya adı ve banka açıklaması güvenilmez girdidir.
- Kullanıcı girdisi `Markup`/safe olarak işaretlenmez.
- Content-Security-Policy kademeli olarak uygulanır; inline script/style bağımlılığı azaltılır.
- `X-Content-Type-Options: nosniff`, `Referrer-Policy` ve frame koruması ayarlanır.

## 7. SQL injection

SQLAlchemy parametreli sorguları kullanılır. String birleştirmeli SQL yasaktır. Raw SQL zorunluysa bound parameter, review ve test gerekir. Kullanıcı kontrollü sort/column isimleri allowlist'ten seçilir; bind parameter'ın identifier koruması sağlamadığı unutulmaz.

## 8. IDOR ve tenant izolasyonu

- Tenant, hosttan çözülür.
- Her tenant kaydı doğrudan `organization_id` taşır.
- Repository metotları organization scope zorunlu alır.
- Bina/daire membership kapsamı ayrıca uygulanır.
- Parent-child ve organization tutarlılığı sorgu/constraint ile doğrulanır.
- Hata yanıtı yetkisiz kaydın varlığını ifşa etmez.
- Platform super admin için örtülü bypass yoktur.

PostgreSQL Row-Level Security ileride defense-in-depth olarak değerlendirilebilir. Ancak connection pooling, platform işlemleri ve migration operasyonları dikkatle tasarlanmadan erken eklenmemelidir.

## 9. Rate limiting

Öncelikli hedefler:

- Login, forgot/reset password
- Domain doğrulama
- Davet gönderme
- Dosya yükleme
- CSV/Excel import
- Finansal POST işlemlerinde anormal tekrar

Limit anahtarı IP + normalize kullanıcı/tenant bağlamını birlikte değerlendirebilir. Proxy arkasında gerçek IP yalnız güvenilir Nginx header'ından alınır. Tek süreçli memory store production için yeterli değildir; çok worker uyumlu store gerekir. Limit kullanıcıya anlaşılır mesaj ve `Retry-After` üretir.

## 10. Dosya yükleme güvenliği

- Yalnız PDF, JPG/JPEG ve PNG
- Dosya başına 10 MB; Nginx ve Flask seviyesinde aynı sınır
- Uzantı + beyan edilen MIME + magic byte kontrolü
- Güvenli, sistem üretimli storage key
- Original filename yalnız metadata/gösterim amaçlı
- Public static dizini dışında depolama
- İndirme yalnız yetkili Flask endpoint'inden; organization ve ilişkili entity kapsamı doğrulanarak yapılır
- Görsel/PDF işleme yapılırsa parser sandbox/limitleri
- Arşiv dosyaları varsayılan reddedilir
- SHA-256 checksum ve audit
- İndirmede güvenli `Content-Disposition` ve `nosniff`
- CSV/Excel formül enjeksiyonuna karşı import/export sanitizasyonu

Malware taraması için adapter/hook noktası bulunur; harici antivirüs servisi MVP'de zorunlu değildir. Harici tarama etkin değilken tür/MIME/uzantı ve boyut kontrolleri zorunludur. MVP'de otomatik dosya silme yoktur; retention ileride hukuki ve sözleşmesel ihtiyaca göre yapılandırılır.

## 11. Audit log

Kritik eylemler en az şu alanlarla yazılır: organization, actor, action, entity, old/new güvenli değerler, IP, user-agent, request ID, UTC zaman.

Zorunlu olaylar:

- Kullanıcı oluşturma/pasifleştirme ve yetki değişikliği
- Organization, branding ve domain değişiklikleri
- Borç, ödeme, düzeltme ve ters kayıt
- Banka hareketi ve import
- Gider, eşleştirme ve belge
- Duyuru yayınlama

Audit append-only'dir. Uygulamanın normal DB rolü update/delete yetkisine sahip olmamalıdır. Secret, parola hash'i, token, cookie ve tam hassas belge içeriği kaydedilmez. Audit erişimi de audit edilir.

## 12. Secret yönetimi

- Secret'lar repoya, image'a, loga veya Markdown'a yazılmaz.
- Development için Git dışı environment dosyası; production için systemd credentials/environment file veya uygun secret store.
- Dosya izinleri en az yetkili kullanıcıyla sınırlandırılır.
- Database URL, Flask secret, SMTP/push/banka anahtarları ayrı secret'lardır.
- Rotation prosedürü ve sahibi tanımlanır.
- `.env.example` ileride yalnız anahtar adları ve güvenli örnekler içerir.

## 13. Yedekleme

### PostgreSQL

- Günlük otomatik yedek; başlangıç RPO hedefi 24 saat
- Offsite ve şifreli kopya
- Retention environment/configuration ile yönetilir; kesin günlük/haftalık/aylık süre production operasyon planında belirlenir
- Yedek başarısı alarmı
- Düzenli staging geri yükleme testi
- Point-in-time recovery ihtiyacı RPO'ya göre değerlendirilir

### Belgeler

- Storage içeriği günlük, metadata ile tutarlı biçimde yedeklenir.
- Sürümleme/immutable backup tercih edilir.
- Veritabanı ve storage restore sıralaması runbook'ta yer alır.
- Checksum ile geri yüklenen dosya bütünlüğü örneklenir.

DB ve dosya yedekleri yalnız uygulama VPS'sinde tutulmaz; en az bir şifreli uzak/off-site kopya zorunludur. Yedek alınmış olması yeterli değildir; düzenli restore testi yapılır ve ölçülen geri yükleme süresi başlangıç RTO hedefi olan 4 saatle karşılaştırılır.

## 14. Loglama ve rotation

- JSON veya tutarlı yapılandırılmış log
- Her istekte request ID
- Tenant için mümkünse internal organization ID; hostname kontrollü
- Parola, token, cookie, authorization header ve belge içeriği yok
- IP ve user-agent için veri minimizasyonu/retention
- journald veya dosya tabanlı log rotation
- Disk doluluk alarmı
- Uygulama error tracking entegrasyonu

Audit log ile operasyon logu farklı amaç taşır ve birbirinin yerine geçmez.

## 15. Health check

- `/health/live`: süreç yanıt veriyor; pahalı dependency çağrısı yapmaz.
- `/health/ready`: veritabanı ve kritik bağımlılıkların kısa süreli kontrolü.
- Hassas version/config bilgisi anonim yanıtta gösterilmez.
- Nginx veya yerel monitor bu endpoint'leri kullanır.
- Storage/banka gibi opsiyonel servis arızaları ayrı degraded metriği olabilir.

## 16. Production güncelleme süreci

1. Değişiklik CI testleri ve güvenlik kontrollerinden geçer.
2. Sürüm artifact'ı immutable ve etiketlidir.
3. Production öncesi veritabanı ve gerekli dosya yedeği doğrulanır.
4. Migration staging'de gerçekçi veriyle test edilir.
5. Bakım/uyumluluk planına göre migration çalıştırılır.
6. Yeni Gunicorn sürümü kontrollü restart/reload edilir.
7. Health ve tenant bazlı smoke test yapılır.
8. Hata oranı/log/latency izlenir.
9. Sürüm ve işlemi yapan kişi deployment kaydına yazılır.

Uygulama kodu mümkün olduğunca expand/migrate/contract yaklaşımıyla bir önceki şemayla kısa süre uyumlu olmalıdır.

## 17. Geri alma stratejisi

- Uygulama artifact'ı önceki sürüme hızlı dönebilir.
- Geriye uyumsuz migration tek adımda yayınlanmaz.
- Veri silen migration öncesinde ayrı yedek ve açık onay gerekir.
- Migration downgrade güvenli değilse ileri düzeltme veya restore runbook'u kullanılır.
- Restore, son çaredir ve RPO kadar veri kaybı yaratabileceği için olay komutasıyla yapılır.
- Nginx/domain değişikliği config sürümü ve atomic symlink/reload yöntemiyle geri alınabilir.

## 18. Tenant izolasyonu testleri

Her kaynak için en az iki organization ve çakışan görünen iş verisi oluşturulur. Test matrisi:

- Liste: diğer tenant satırı görünmez.
- Detay: diğer tenant ID'si 404/uygun ret verir.
- Yazma: URL parent'ı başka tenant ise başarısız.
- Güncelleme/arşiv/ters kayıt: çapraz tenant başarısız.
- Dosya: metadata ve storage indirmesi başarısız.
- Search/export/import: scope dışına taşmaz.
- Membership revoke: mevcut session sonraki kontrolde erişemez.
- Host değişimi: session başka tenant'a taşınmaz.
- Background task: yanlış/eksik tenant kimliğiyle çalışmaz.

Bu negatif testler yeni tenant tablosu veya route'u için merge koşuludur.

## 19. Production altyapı sertleştirmesi

- Ubuntu güvenlik güncellemeleri ve minimum paketler
- SSH key, root login kısıtı, firewall
- Nginx/Gunicorn/PostgreSQL ayrı ve en az yetkili servis hesapları
- PostgreSQL public internete kapalı
- systemd restart limitleri ve kaynak limitleri
- Saat senkronizasyonu
- Disk, bellek, CPU, sertifika, yedek ve hata alarmı
- Development debug kapalı; stack trace kullanıcıya kapalı
- İlk MVP ve ilk müşterilerde tek Ubuntu VPS kabul edilir; PostgreSQL aynı VPS'de çalışabilir. Bu açık bir single point of failure'dır.
- Uygulama state'i taşınabilir tutulur; storage adapter korunur. Büyümede uygulama, PostgreSQL ve obje depolama ayrılabilir.
- Bu geçiş için baştan Kubernetes kurulmaz.

## 20. Varsayımlar, açık kararlar ve riskler

Varsayımlar:

- İlk deployment tek Ubuntu VPS'tir.
- Nginx ve PostgreSQL aynı sunucuda olabilir; erişim loopback ile sınırlıdır.
- Production ve development veri/secret'ları tamamen ayrıdır.

Açık kararlar:

- Kesin backup retention gün/hafta/ay değerleri
- Rate limit store seçimi
- Harici malware scanner'ın ileride devreye alınma eşiği ve hata politikası
- Error tracking ürünü ve veri yerleşimi
- Güvenlik olayı iletişim/incident response sorumluları
- PostgreSQL RLS'nin ileride devreye alınma ölçütleri

Başlıca riskler:

- Tek VPS açıkça kabul edilmiş tek hata noktasıdır; off-site yedek availability sağlamaz fakat felaket kurtarmayı mümkün kılar.
- Backup restore edilmeden güvenilir sayılmaz.
- Proxy header yanlış yapılandırması host/IP kontrollerini bozar.
- Audit içinde gereksiz kişisel veri saklanması yeni risk yaratır.
- Güvenlik yamalarının gecikmesi internet-facing sistemi savunmasız bırakır.

## 21. Uygulanan auth güvenlik durumu

- Flask-Login user loader her istekte güncel User kaydını UUID ile yükler.
- Korumalı route'lar user ve membership durumunu yeniden doğrular;
  inactive/locked user session'ı kapatılır.
- Login ve logout Flask-WTF CSRF korumasındadır; CSRF hatası token veya teknik
  ayrıntı göstermeyen 400 yanıtı verir.
- Session ve remember cookie host-only, HttpOnly ve SameSite=Lax'tır; production
  Secure zorunludur.
- Login IP başına varsayılan `5/minute;30/hour` ile sınırlıdır. Memory storage
  tek process development/test içindir; çok worker production ortak storage
  gerektirir. Redis henüz kurulmamıştır.
- Başarılı login güvenli kimlik/tenant bağlamıyla loglanır; parola, hash ve CSRF
  token loglanmaz.
- MFA henüz uygulanmamıştır. Platform super admin MFA ilk production yayını
  öncesinde tamamlanmalıdır.
