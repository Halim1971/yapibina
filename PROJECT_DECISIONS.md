# Yapıbina Proje Kararları

Bu belge Architecture Decision Record (ADR) özeti olarak yaşatılmalıdır. Kararlar değiştiğinde eski gerekçe silinmemeli; tarihli yeni karar eklenmeli ve önceki kararın durumu `superseded` yapılmalıdır.

## D-001 — Ürün kapsamı dört resident işleviyle sınırlıdır

- **Karar:** Resident ürünü Ekstrem, Banka, Giderler ve Duyurular modüllerinden oluşur.
- **Gerekçe:** Hedef müşteri karmaşık yönetim/ERP ürünlerini fazla bulan küçük ve orta ölçekli yapılardır.
- **Alternatifler:** Genel muhasebe, CRM, satın alma ve kapsamlı ERP.
- **Neden seçilmedi:** Ürün sadeliğini, teslim süresini ve güvenilirliği olumsuz etkiler.
- **İleride yeniden değerlendirme koşulu:** Birden fazla müşteri aynı ek işlevi doğrulanmış ihtiyaç olarak talep eder ve dört işlev deneyimi bozulmadan ayrı modül olabilir.

## D-002 — Organization tenant sınırıdır

- **Karar:** Tenant kökü `organization`; bir bina tam olarak bir organization'a aittir.
- **Gerekçe:** Yönetim firması çok sayıda binayı tek marka ve kullanıcı yönetimi altında işletir.
- **Alternatifler:** Binayı tenant yapmak; kullanıcıyı tenant yapmak.
- **Neden seçilmedi:** Organization çapındaki yönetim, marka, domain ve çoklu bina senaryolarını parçalar.
- **İleride yeniden değerlendirme koşulu:** Hukuki/veri yerleşimi gereksinimi bina bazında fiziksel ayrım zorunlu kılarsa.

## D-003 — Tek PostgreSQL veritabanı ve ortak schema

- **Karar:** MVP'de tenant'lar tek DB/common schema içinde `organization_id` ile izole edilir.
- **Gerekçe:** Operasyon ve migration sadeliği, hedef ölçek için yeterli verim.
- **Alternatifler:** Tenant başına schema; tenant başına veritabanı.
- **Neden seçilmedi:** İlk aşamada provisioning, migration, backup ve bağlantı yönetimi maliyeti yüksektir.
- **İleride yeniden değerlendirme koşulu:** Yasal izolasyon, büyük tenant performansı, veri yerleşimi veya kurumsal sözleşme gerektirirse.

## D-004 — Tenant kapsamlı tablolarda doğrudan organization_id

- **Karar:** Alt ilişkiden türetilebilse bile tenant verisi doğrudan `organization_id` taşır.
- **Gerekçe:** Scoped sorgular, indeksleme, audit ve defense-in-depth kolaylaşır.
- **Alternatifler:** Organization'ı yalnız building/apartment join'iyle türetmek.
- **Neden seçilmedi:** Filtre unutma ve karmaşık sorgu riski yükselir.
- **İleride yeniden değerlendirme koşulu:** Ölçülmüş veri/performans sonucu farklı fiziksel tenant modeli seçilirse.

## D-005 — Host bazlı tenant resolution

- **Karar:** Aktif tenant yalnız doğrulanmış, aktif ve exact-match hostname kaydından çözülür.
- **Gerekçe:** White-label özel domain gereksinimi ve güvenli tenant seçimi.
- **Alternatifler:** URL path, form/query `organization_id`, session tenant değeri.
- **Neden seçilmedi:** Path MVP dışıdır; istemci değerleri spoof edilebilir ve domain deneyimini karşılamaz.
- **İleride yeniden değerlendirme koşulu:** Mobil/API istemcisi veya path tenant için açık ürün gereksinimi doğarsa; ayrı güvenli tenant seçme protokolü tasarlanır.

## D-006 — Geçici ve özel domain birlikte desteklenir

- **Karar:** İlk erişim `slug.yapibina.com`, tercih edilen kalıcı erişim `panel.musterialanadi.com`.
- **Gerekçe:** Hızlı onboarding ile güçlü white-label deneyimini birlikte sağlar.
- **Alternatifler:** Yalnız Yapıbina domaini; yalnız müşteri domaini; path tabanlı panel.
- **Neden seçilmedi:** İlki white-label'ı zayıflatır, ikincisi onboarding'i geciktirir, path MVP kapsamı dışıdır.
- **İleride yeniden değerlendirme koşulu:** DNS operasyon maliyeti veya müşteri talebi farklı model gerektirirse.

## D-007 — Flask application factory ve blueprint modülerliği

- **Karar:** Uygulama factory ile kurulur; auth/platform/organization/building/resident blueprint'lerine ayrılır.
- **Gerekçe:** Test edilebilirlik, environment ayrımı ve rol bağlamlarının netliği.
- **Alternatifler:** Global tek Flask app; tek monolitik blueprint.
- **Neden seçilmedi:** Import side effect, test izolasyonu ve büyüyen route karmaşası yaratır.
- **İleride yeniden değerlendirme koşulu:** Uygulama sınırları ayrı deploy edilen servislere bölünecek ölçüde bağımsızlaşırsa.

## D-008 — Service ve tenant-scoped repository katmanları

- **Karar:** İş kuralları service/use-case, veri erişimi scoped repository/query katmanındadır.
- **Gerekçe:** Route'ları ince tutar, tenant filtresini merkezileştirir, işlemleri test edilebilir yapar.
- **Alternatifler:** Route'lardan doğrudan SQLAlchemy; aktif kayıt deseni.
- **Neden seçilmedi:** Yetki/transaction tekrarına ve tenant sızıntısı riskine yol açar.
- **İleride yeniden değerlendirme koşulu:** Katmanların ölçülmüş gereksiz karmaşıklık yarattığı dar alanlarda, güvenlik invariant'ları korunarak sadeleştirme.

## D-009 — Membership tabanlı roller

- **Karar:** Organization, building ve apartment ilişkileri ara tablolarda; kullanıcı global kimliktir.
- **Gerekçe:** Bir kullanıcının birden fazla organization, bina veya daireyle ilişkisini destekler.
- **Alternatifler:** `user.role`, `user.organization_id`, tek daire FK'si.
- **Neden seçilmedi:** Çoklu ilişki ve tarihsel üyelik gereksinimini karşılamaz.
- **İleride yeniden değerlendirme koşulu:** Daha ayrıntılı permission set/ABAC ihtiyacı oluşursa policy modeli genişletilir.

## D-010 — Append-only basit finansal ledger

- **Karar:** Posted tahakkuk/ödeme hareketleri fiziksel silinmez veya değiştirilmez; hata ters/düzeltme kaydıyla giderilir.
- **Gerekçe:** Şeffaflık, audit edilebilirlik ve bakiye güvenilirliği.
- **Alternatifler:** Mutable borç/ödeme satırları; tam çift taraflı genel muhasebe.
- **Neden seçilmedi:** Mutable kayıt iz kaybettirir; genel muhasebe hedef kapsamı aşar.
- **İleride yeniden değerlendirme koşulu:** Yasal muhasebe entegrasyonu, farklı mahsup stratejileri veya çift taraflı muhasebe gereksinimi oluşursa ledger genişletilir.

## D-011 — Numeric ve Decimal para modeli

- **Karar:** PostgreSQL `Numeric`, Python `Decimal`; `float` kullanılmaz.
- **Gerekçe:** Ondalık para işlemlerinde deterministik doğruluk.
- **Alternatifler:** Float; kuruşu integer olarak saklamak.
- **Neden seçilmedi:** Float yuvarlama hatalıdır; integer geçerli olsa da çoklu precision/entegrasyonlarda ek dönüşüm yükü yaratır.
- **İleride yeniden değerlendirme koşulu:** Çok para birimli ve farklı minor-unit gereksinimi oluşursa money value object tasarlanır.

## D-012 — Bakiye ledger'dan türetilir

- **Karar:** Ledger doğruluk kaynağıdır; saklanan bakiye varsa yalnız yeniden üretilebilir projection/cache olur.
- **Gerekçe:** Drift ve yarış koşullarını azaltır.
- **Alternatifler:** Apartment üzerinde mutable balance.
- **Neden seçilmedi:** Transaction hatalarında ledger ile bakiye ayrışabilir.
- **İleride yeniden değerlendirme koşulu:** Ölçülen sorgu maliyeti hedefleri aşarsa kontrollü projection eklenir.

## D-013 — Storage portu ve private depolama

- **Karar:** İş mantığı `StorageService` portuna bağlıdır; MVP yerel private adapter, gelecek S3 uyumlu adapter.
- **Gerekçe:** Güvenli indirme ve depolama sağlayıcısı taşınabilirliği.
- **Alternatifler:** Public static upload klasörü; doğrudan S3 SDK bağımlılığı.
- **Neden seçilmedi:** İlki yetkiyi atlar, ikincisi iş mantığını sağlayıcıya bağlar.
- **İleride yeniden değerlendirme koşulu:** Dağıtık deployment, kapasite veya dayanıklılık yerel storage'ı yetersiz kılarsa S3 adapter aktive edilir.

## D-014 — Banka provider/adapter sınırı

- **Karar:** MVP manuel ve CSV/Excel import kullanır; normalize importer ve gelecekteki `BankProvider` portu planlanır.
- **Gerekçe:** Bugünkü kapsamı sade tutarken banka bağımlılığını çekirdekten ayırır.
- **Alternatifler:** İlk sürümde doğrudan banka API'leri; banka formatını service'e gömmek.
- **Neden seçilmedi:** API'ler kapsam, güvenlik ve operasyon yükünü artırır; gömülü format bakım zorluğu yaratır.
- **İleride yeniden değerlendirme koşulu:** Belirli banka entegrasyonu ticari olarak doğrulanır ve sözleşme/API erişimi sağlanırsa.

## D-015 — Ortak template ve CSS custom property teması

- **Karar:** Tek UI/template sistemi; organization teması doğrulanmış CSS değişkenleri ve asset'lerle override edilir.
- **Gerekçe:** White-label sunarken müşteri başına kod çatallanmasını önler.
- **Alternatifler:** Müşteri başına HTML/CSS; sınırsız tema motoru.
- **Neden seçilmedi:** Bakım, güvenlik, test ve upgrade maliyeti büyür.
- **İleride yeniden değerlendirme koşulu:** Paketlenmiş, sınırlı layout varyantları ticari ihtiyaç olarak doğrulanırsa.

## D-016 — Server-rendered Jinja ve seçici HTMX

- **Karar:** İlk UI server-rendered Jinja; yalnız gerçek fayda sağladığında HTMX/sade JavaScript.
- **Gerekçe:** Basit operasyon, erişilebilirlik ve hedef ürün için düşük istemci karmaşıklığı.
- **Alternatifler:** SPA framework; tamamen statik formlar.
- **Neden seçilmedi:** SPA gereksiz build/state/API yükü getirir; seçici etkileşim yine faydalı olabilir.
- **İleride yeniden değerlendirme koşulu:** Ölçülmüş kullanıcı akışları zengin client state veya bağımsız API istemcisi gerektirirse.

## D-017 — Append-only audit

- **Karar:** Kritik işlemler organization/actor/request bağlamıyla append-only audit tablosuna yazılır.
- **Gerekçe:** Finansal ve yetki değişikliklerinin izlenebilirliği.
- **Alternatifler:** Yalnız uygulama logları; tüm tablo değişikliklerini sınırsız kaydetmek.
- **Neden seçilmedi:** Operasyon logu iş audit'i değildir; sınırsız kayıt secret/PII ve hacim riski yaratır.
- **İleride yeniden değerlendirme koşulu:** Regülasyon WORM, harici SIEM veya daha uzun retention gerektirirse.

## D-018 — Tek Ubuntu VPS production temeli

- **Karar:** Nginx → Gunicorn → Flask → PostgreSQL, systemd yönetimiyle doğrudan Ubuntu VPS.
- **Gerekçe:** Belirtilen işletim hedefi, kontrol ve platform bağımsızlığı.
- **Alternatifler:** Heroku/Render/Railway; ilk günden Kubernetes.
- **Neden seçilmedi:** Platform bağımlılığı veya hedef ölçek için aşırı operasyon karmaşıklığı.
- **İleride yeniden değerlendirme koşulu:** Availability, yatay ölçek, ekip/dağıtım sıklığı veya müşteri SLA'sı tek VPS'i aşarsa.

## D-019 — UTC saklama, Europe/Istanbul sunumu

- **Karar:** Veritabanı zamanları UTC `timestamptz`; kullanıcı görünümü Europe/Istanbul ve Türkçe biçim.
- **Gerekçe:** Tutarlı sıralama/entegrasyon ve doğru yerel deneyim.
- **Alternatifler:** Yerel naive datetime saklamak.
- **Neden seçilmedi:** DST, sunucu ayarı ve entegrasyonlarda belirsizlik yaratır.
- **İleride yeniden değerlendirme koşulu:** Organization bazında farklı timezone/locale desteği etkinleşirse mevcut alanlar üzerinden genişletilir.

## D-020 — API ve Web Push MVP dışında

- **Karar:** Bildirim için uygulama içi duyuru/okundu kaydı kurulur; provider portu ilerisi için ayrılır. Genel public API yapılmaz.
- **Gerekçe:** Dört temel işlevi güvenle yayınlamaya odaklanmak.
- **Alternatifler:** İlk günden Web Push ve REST/GraphQL API.
- **Neden seçilmedi:** Kimlik, izin, retry, client ve operasyon kapsamını büyütür.
- **İleride yeniden değerlendirme koşulu:** Mobil uygulama, entegrasyon müşterisi veya bildirim etkileşimi doğrulanırsa.

## D-021 — PostgreSQL RLS ertelenmiş defense-in-depth seçeneğidir

- **Karar:** MVP'de zorunlu scoped repository + constraint kullanılır; RLS hemen etkinleştirilmez.
- **Gerekçe:** RLS güçlüdür ancak connection pooling, platform yetkisi, migration ve test tasarımı yanlışsa sahte güven yaratabilir.
- **Alternatifler:** İlk günden RLS; yalnız UI filtresi.
- **Neden seçilmedi:** İlki operasyonel tasarım hazır değilken karmaşıktır; ikincisi kabul edilemez derecede güvensizdir.
- **İleride yeniden değerlendirme koşulu:** DB rol ayrımı, session tenant binding ve kapsamlı RLS test altyapısı hazır olduğunda.

## D-022 — Bilinmeyen host fail-closed

- **Karar:** Kayıtsız veya doğrulanmamış host tenant'a düşmez; markasız 421/404 ile reddedilir.
- **Gerekçe:** Host spoofing ve yanlış tenant/marka gösterimini önler.
- **Alternatifler:** Varsayılan organization; merkezi siteye dinamik redirect.
- **Neden seçilmedi:** Veri sızıntısı ve open redirect riski.
- **İleride yeniden değerlendirme koşulu:** Merkezi yönlendirme UX'i istenirse yalnız sabit allowlisted hedefle.

## D-023 — Fiziksel silme yerine durum/arşivleme

- **Karar:** Finansal/audit kaydı silinmez; diğer kritik varlıklar önce pasifleştirilir veya arşivlenir.
- **Gerekçe:** İzlenebilirlik, yanlış silmeden kurtulma ve yasal saklama.
- **Alternatifler:** Hard delete; tüm tablolar için sınırsız soft delete.
- **Neden seçilmedi:** Hard delete iz kaybettirir; her yerde soft delete sorgu karmaşası ve gereksiz retention yaratır.
- **İleride yeniden değerlendirme koşulu:** Onaylı veri retention ve KVKK silme/anonimleştirme politikası kesinleştiğinde tablo bazında.

## D-024 — Resident yalnız aktif apartment membership ile erişir

- **Karar:** Resident yalnız aktif üyeliği bulunan daireyi/binasını görür; sona ermiş üyelik geçmiş veriye otomatik erişim vermez ve membership satırı fiziksel silinmez.
- **Gerekçe:** Güncel yetki sınırını kesin ve denetlenebilir tutmak; üyelik geçmişini korumak.
- **MVP kapsamı:** Organization admin ve yetkili building manager üyeliği aktif/pasif yapar; `starts_on`, `ends_on`, status değişikliği ve audit tutulur.
- **Sonraya bırakılan alternatif:** Eski sakin için süreli geçmiş ekstre veya seçili belge paylaşımı.
- **Yeniden değerlendirme koşulu:** Hukuki zorunluluk veya doğrulanmış müşteri ihtiyacı geçmiş erişim politikası gerektirirse.

## D-025 — Tahakkuk, dönem ve toplu oluşturma modeli

- **Karar:** Borç türü `aidat/ek_borc/duzeltme/diger`, `due_date` zorunlu, `period_year/month` isteğe bağlıdır; manuel ve toplu tahakkuk desteklenir.
- **Gerekçe:** Vade ve dönem görünürlüğünü sağlarken MVP'yi gereksiz otomasyondan korumak.
- **MVP kapsamı:** Yetkili yönetici tekil veya toplu tahakkuk oluşturur; Numeric/Decimal ve append-only kuralları geçerlidir.
- **Sonraya bırakılan alternatif:** Otomatik tekrarlayan aidat, gecikme faizi ve gecikme cezası.
- **Yeniden değerlendirme koşulu:** Pilot kullanımda düzenli tahakkuk iş yükü veya onaylanmış ceza politikası bunu gerektirirse.

## D-026 — Kısmi ödeme ve açık allocation kaydı

- **Karar:** Ödeme bir veya daha fazla borca `payment_allocation` ile dağıtılır; varsayılan sıra en eski vadesi geçmiş, sonra en eski açık borçtur. Dağıtılmayan tutar kredi/alacak bakiyesidir.
- **Gerekçe:** Kısmi ödeme ve fazla ödemeyi kayıpsız, izlenebilir ve deterministik yönetmek.
- **MVP kapsamı:** Charge, payment ve allocation ayrı append-only kayıtlardır; toplamlar service ve deferred DB kontrolüyle korunur; hatalar ters kayıtla düzeltilir.
- **Sonraya bırakılan alternatif:** Kullanıcıya gelişmiş allocation stratejileri, otomatik mahsup politikaları ve genel muhasebe.
- **Yeniden değerlendirme koşulu:** Hukuki/muhasebesel politika veya pilot müşteriler farklı mahsup önceliği gerektirirse.

## D-027 — Banka hareketi ve gider arasında isteğe bağlı bire bir eşleşme

- **Karar:** MVP'de bir banka hareketi en fazla bir giderle, bir gider en fazla bir banka hareketiyle eşleşir; ilişki nullable'dır.
- **Gerekçe:** Şeffaf mutabakatı basit, anlaşılır ve constraint ile korunabilir tutmak.
- **MVP kapsamı:** Aynı organization/building kontrolü ve nullable FK üzerinde partial unique constraint.
- **Sonraya bırakılan alternatif:** Kısmi, bölünmüş ve çoklu reconciliation için junction tablo.
- **Yeniden değerlendirme koşulu:** Gerçek banka hareketlerinin toplu ödeme veya gider bölme senaryoları pilotta doğrulanırsa.

## D-028 — MVP dosya politikası

- **Karar:** Yalnız PDF, JPG/JPEG ve PNG; en fazla 10 MB; private storage, güvenli key ve yetkili Flask indirme endpoint'i.
- **Gerekçe:** Gider belgelerinin temel formatlarını desteklerken saldırı yüzeyini ve operasyon yükünü sınırlamak.
- **MVP kapsamı:** Uzantı+MIME kontrolü, organization/entity yetkisi, checksum, audit; otomatik silme yok; malware adapter/hook var.
- **Sonraya bırakılan alternatif:** Harici antivirüs zorunluluğu, ek dosya türleri, otomatik retention/silme.
- **Yeniden değerlendirme koşulu:** Risk değerlendirmesi, hukuki saklama politikası veya müşteri dosya ihtiyaçları değişirse.

## D-029 — Günlük off-site yedek, RPO 24 saat ve RTO 4 saat

- **Karar:** PostgreSQL ve dosyalar günlük yedeklenir; en az bir şifreli off-site kopya tutulur. Başlangıç RPO 24 saat, RTO 4 saattir.
- **Gerekçe:** Tek VPS arızasında kabul edilebilir ilk felaket kurtarma hedefi sağlamak.
- **MVP kapsamı:** Otomatik günlük yedek, config tabanlı retention, başarı alarmı ve düzenli restore testi.
- **Sonraya bırakılan alternatif:** PITR, sıcak standby, çok bölgeli replikasyon ve daha düşük RPO/RTO.
- **Yeniden değerlendirme koşulu:** SLA, veri hacmi, işlem sıklığı veya ölçülen restore süresi hedefleri aşarsa.

## D-030 — MFA ve break-glass destek erişimi

- **Karar:** Platform super admin MFA production öncesi zorunlu; organization admin MFA desteklenir ve zorunlu yapılabilir. Destek erişimi süreli, gerekçeli, açık yetkili ve audit'li break-glass'tır.
- **Gerekçe:** En yüksek ayrıcalıklı hesapları ve tenant gizliliğini korumak.
- **MVP kapsamı:** Bu authentication aşamasında MFA uygulanmamıştır. Platform admin MFA enforcement production öncesi zorunlu sonraki teslimattır; kullanıcı parolası hiçbir zaman görünmez.
- **Sonraya bırakılan alternatif:** Organization admin için varsayılan zorunlu MFA; building manager/resident MFA; gelişmiş PAM.
- **Yeniden değerlendirme koşulu:** Tehdit modeli, sözleşme, regülasyon veya hesap ele geçirme bulguları daha geniş MFA gerektirirse.

## D-031 — Domain/SSL/Nginx MVP'de kontrollü manuel provision edilir

- **Karar:** Domain akışı `pending/awaiting_dns/dns_verified/ssl_pending/active/failed/suspended` state machine'iyle, yetkili operatör tarafından DNS kontrolü, Certbot, Nginx test ve reload sırasıyla yürütülür.
- **Gerekçe:** İlk müşteri sayısında güvenli operasyonu tam otomasyon karmaşıklığı olmadan sağlamak.
- **MVP kapsamı:** Audit'li state geçişleri, config şablonu, zorunlu configuration test, son bilinen iyi config ve kontrollü reload.
- **Sonraya bırakılan alternatif:** Tam otomatik ACME ve Nginx provisioner.
- **Yeniden değerlendirme koşulu:** Domain sayısı veya onboarding sıklığı manuel operasyonu hata/kapasite sınırına getirirse.

## D-032 — İlk müşteriler için tek Ubuntu VPS

- **Karar:** Flask/Gunicorn/Nginx ve başlangıçta PostgreSQL tek Ubuntu VPS'de çalışabilir; bu açık bir single point of failure'dır.
- **Gerekçe:** İlk ölçek için anlaşılır ve ekonomik işletim; gereksiz erken dağıtık sistemden kaçınma.
- **MVP kapsamı:** Off-site yedek, taşınabilir app state, storage adapter ve bileşenleri ayırmaya uygun yapı.
- **Sonraya bırakılan alternatif:** Ayrı PostgreSQL, obje depolama, çoklu uygulama sunucusu; Kubernetes.
- **Yeniden değerlendirme koşulu:** SLA, kapasite, bakım penceresi veya arıza etkisi tek VPS sınırını aşarsa; geçiş için Kubernetes zorunlu varsayılmaz.

## D-033 — UUID primary key

- **Karar:** Tenant çekirdeğindeki tüm tablolar uygulama tarafında üretilen UUID primary key kullanır.
- **Gerekçe:** Tahmin edilebilir ardışık kimliklerden kaçınmak ve PostgreSQL/SQLite taşınabilirliğini korumak.
- **MVP kapsamı:** SQLAlchemy `Uuid(as_uuid=True)` ve `uuid4` default'u.
- **Sonraya bırakılan alternatif:** UUIDv7 veya veritabanı tarafında UUID üretimi.
- **Yeniden değerlendirme koşulu:** Sıralı yazma performansı ölçülmüş bir darboğaz oluşturursa.

## D-034 — Taşınabilir string enum

- **Karar:** Enum'lar `SQLAlchemy Enum(native_enum=False)` ve check constraint olarak saklanır.
- **Gerekçe:** PostgreSQL native enum migration zorluğunu azaltmak ve SQLite test uyumluluğu sağlamak.
- **MVP kapsamı:** User, organization, membership, domain type ve domain state alanları.
- **Sonraya bırakılan alternatif:** PostgreSQL native enum veya lookup tabloları.
- **Yeniden değerlendirme koşulu:** Enum metadata, çeviri veya dinamik yönetim gereksinimi oluşursa.

## D-035 — Organization ve building üyelikleri ayrıdır

- **Karar:** Organization rolü OrganizationMembership, bina operasyon rolü BuildingMembership ile temsil edilir.
- **Gerekçe:** Organization admin'in tüm tenant kapsamını, building manager'ın yalnız atanmış binaları yönetmesini açıkça ayırmak.
- **MVP kapsamı:** Organization admin/member ve building manager/staff rolleri ayrı tablolardadır.
- **Sonraya bırakılan alternatif:** Tek genel polymorphic role tablosu veya tam RBAC permission matrisi.
- **Yeniden değerlendirme koşulu:** Rol sayısı ve kaynak bazlı izinler mevcut modeli belirgin biçimde aşarsa.

## D-036 — Tarihsel apartment membership

- **Karar:** ApartmentMembership fiziksel silinmez; aktiflik ve başlangıç/bitiş zamanı taşır. Aynı kullanıcı daha sonraki ayrı dönemde tekrar ilişkilendirilebilir.
- **Gerekçe:** Sakin geçmişini korurken yalnız güncel aktif ilişkinin erişim vermesini sağlamak.
- **MVP kapsamı:** Service seviyesinde timezone-aware dönem ve aktif dönem çakışma kontrolü.
- **Sonraya bırakılan alternatif:** PostgreSQL exclusion constraint ile veritabanı seviyesinde zaman aralığı çakışma koruması.
- **Yeniden değerlendirme koşulu:** Eşzamanlı membership yazma hacmi service kontrolünde yarış koşulu riski yaratırsa.

## D-037 — Organization başına tek primary domain

- **Karar:** Her organization için en fazla bir `is_primary=true` domain bulunur.
- **Gerekçe:** Canonical host davranışını belirsiz bırakmamak.
- **MVP kapsamı:** PostgreSQL ve SQLite partial unique index ile service ön kontrolü birlikte uygulanır.
- **Sonraya bırakılan alternatif:** Domain tipine göre birden fazla primary veya öncelik sırası.
- **Yeniden değerlendirme koşulu:** Farklı ürün kanalları ayrı canonical domain gerektirirse.

## D-038 — Organization admin tüm organization binalarına erişir

- **Karar:** Aktif organization admin, her bina için BuildingMembership gerekmeksizin kendi organization'ındaki tüm bina operasyonlarına yetkilidir.
- **Gerekçe:** Organization admin tenant yöneticisidir; bina başına yinelenen atama gereksiz ve hataya açıktır.
- **MVP kapsamı:** Service/policy kontrolünde organization membership tenant sınırı olarak değerlendirilir; başka organization erişimi reddedilir.
- **Sonraya bırakılan alternatif:** Organization admin'e bina bazlı kısıt veya özel permission set.
- **Yeniden değerlendirme koşulu:** Büyük yönetim firmalarında departman/bölge bazlı yetki ayrımı gerekirse.

## D-039 — Host ve membership birlikte login sınırıdır

- **Karar:** Tenant login aktif domain context ve geçerli OrganizationMembership; platform login aktif platform super admin gerektirir.
- **Gerekçe:** Doğru parola tek başına başka organization veya platform erişimi sağlamamalıdır.
- **MVP kapsamı:** Platform ve tenant login ayrımı ile genel, hesap ifşa etmeyen hata.
- **Sonraya bırakılan alternatif:** Break-glass destek erişimi ve organization seçici.
- **Yeniden değerlendirme koşulu:** Onaylı destek veya çoklu organization geçiş akışı tasarlandığında.

## D-040 — Session yetkinin doğruluk kaynağı değildir

- **Karar:** Korumalı her istekte User, tenant ve membership durumu yeniden doğrulanır.
- **Gerekçe:** Pasifleştirme ve süre bitişinin mevcut session üzerinde hemen etkili olması gerekir.
- **MVP kapsamı:** Inactive/locked user session kapatma ve güncel membership policy sorguları.
- **Sonraya bırakılan alternatif:** Merkezi session store ve toplu session revocation.
- **Yeniden değerlendirme koşulu:** Çok cihazlı session yönetimi veya merkezi revocation gerektiğinde.

## D-041 — Tenant dışı kaynak 404, tenant içi yetki eksikliği 403

- **Karar:** Scoped sorguda bulunmayan başka tenant kaynağı 404; aynı tenant'taki yetersiz rol 403 üretir.
- **Gerekçe:** IDOR denemesinde başka tenant kaynağının varlığını ifşa etmemek.
- **MVP kapsamı:** Building ve Apartment resource decorator'ları.
- **Sonraya bırakılan alternatif:** Tüm yetki retlerinde tek tip 404.
- **Yeniden değerlendirme koşulu:** Güvenlik değerlendirmesi daha sıkı kaynak gizleme isterse.

## D-042 — Login rate limit için geçici memory storage

- **Karar:** Login IP başına `5/minute;30/hour`; development/test ve ilk tek-process kullanımda memory storage.
- **Gerekçe:** Redis kurmadan temel brute-force azaltımı sağlamak.
- **MVP kapsamı:** Yapılandırılabilir Flask-Limiter ve genel 429 yanıtı.
- **Sonraya bırakılan alternatif:** Redis veya başka paylaşımlı rate-limit backend'i.
- **Yeniden değerlendirme koşulu:** Production birden fazla Gunicorn worker/process ile yayına alınmadan önce.

## Kodlamadan önce kalan kararlar

Aşağıdakiler uygulanmadan önce sahip ve tarih atanarak karara bağlanmalıdır:

- Kesin CSV/Excel formatları ve Excel'in MVP zorunluluğu
- Platform yönetim hostname'i ve tenant entry hostname'i
- Certbot challenge yöntemi ve manuel production runbook ayrıntıları
- Bilinmeyen host için 421 mi 404 mü
- Geçici/eski domainlerin açık kalma ve karantina süreleri
- Kesin backup retention gün/hafta/ay değerleri
- Toplu tahakkuk batch metadata ve önizleme/idempotency ayrıntıları

## Genel varsayımlar

- İlk sürüm Türkçe, TRY ve Europe/Istanbul odaklıdır.
- Tek deployment bölgesi ve tek Ubuntu VPS ile başlanır.
- Lina Bina Yönetimi yalnız örnektir; hiçbir karar müşteri adına hard-code edilmez.
- Hukuki saklama, KVKK ve finansal belge yükümlülükleri uzman görüşüyle netleştirilecektir.

## Genel riskler

- Tenant scope'un bir sorguda atlanması en kritik veri güvenliği riskidir.
- Finansal immutable kuralların delinmesi güven ve audit bütünlüğünü bozar.
- Domain/DNS/SSL üç farklı sistemde eventual consistency yaratır.
- Tek VPS kullanılabilirlik açısından tek hata noktasıdır.
- Dosya yükleme ve spreadsheet import güvenilmeyen içerik taşır.
- White-label taleplerinin sınırsız özelleştirmeye dönüşmesi ürün sadeliğini bozar.
