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

- **Karar:** MVP'de JSON API veya Web Push yapılmaz. Gelecekteki Announcement,
  Notification ve push sınırları D-067–D-071 kararlarına göre ayrı tasarlanır.
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

## D-043 — Yönetim CRUD işlemleri tenant-scoped service katmanındadır

- **Karar:** Platform işlemleri platform context'te; organization işlemleri
  hosttan çözülen tenant kimliğiyle yürür. Organization kimliği istemci
  formundan kabul edilmez.
- **Gerekçe:** Route veya form manipülasyonunun cross-tenant ilişki kurmasını ve
  IDOR yoluyla veri ifşasını önlemek.
- **MVP kapsamı:** Organization, branding, domain, building, apartment, user ve
  membership yönetimi; scoped arama/sayfalama; status/is_active ile
  pasifleştirme.
- **Sonraya bırakılan alternatif:** Generic repository/permission framework,
  toplu işlemler ve gelişmiş filtreleme.
- **Yeniden değerlendirme koşulu:** Aynı scope/transaction kuralları yeni
  modüllerde anlamlı ölçüde tekrar etmeye başlarsa.

## D-044 — Aidat ve ödeme için dört tabloluk minimum finans çekirdeği

- **Karar:** ChargeBatch, Charge, Payment ve PaymentAllocation kullanılır;
  genel ledger veya çift taraflı muhasebe kurulmaz.
- **Gerekçe:** Apartman aidatı, ödeme ve mahsup ihtiyacını ERP kapsamına
  genişlemeden güvenilir biçimde karşılamak.
- **MVP kapsamı:** Eşit tutarlı toplu aidat, manuel borç, ödeme, kısmi/çoklu
  allocation, oldest-first auto allocation ve sorgudan bakiye.
- **Sonraya bırakılan alternatif:** Hesap planı, muhasebe fişi, çoklu para
  birimi, banka mutabakatı ve daireye özel batch tutarı.
- **Yeniden değerlendirme koşulu:** Yasal muhasebe entegrasyonu veya farklı
  tutarlı tahakkuk ürün gereksinimi oluşursa.

## D-045 — Posted finansal kayıtlar immutable ve reversal tabanlıdır

- **Karar:** Posted Charge/Payment temel alanları değiştirilemez ve fiziksel
  silinmez. Hata reversal ile düzeltilir; allocation bulunan charge doğrudan
  reverse edilemez.
- **Gerekçe:** Finansal geçmişi izlenebilir tutmak ve sessiz bakiye değişimini
  önlemek.
- **MVP kapsamı:** Status, reversed_at, reversal_reason ve ORM immutability
  kontrolü; payment reversal allocation satırlarını hesaplarda etkisiz kılar.
- **Sonraya bırakılan alternatif:** Ayrı reversal hareket modeli ve tam
  append-only event journal.
- **Yeniden değerlendirme koşulu:** Audit/yasal kayıt gereksinimi ayrı ters
  hareket belgesi zorunlu kılarsa.

## D-046 — Para Decimal, bakiye sorgudan hesaplanır

- **Karar:** Para `Numeric(14, 2)`/`Decimal` olarak iki haneye half-up
  yuvarlanır; kalıcı balance kolonu tutulmaz.
- **Gerekçe:** Float hatalarını ve denormalize bakiye drift riskini önlemek.
- **MVP kapsamı:** Tenant-scoped aggregate sorgular, allocation ve reversal
  filtreleri.
- **Sonraya bırakılan alternatif:** Snapshot/cache veya materialized view.
- **Yeniden değerlendirme koşulu:** Ölçülen sorgu hacmi doğruluk kontrollü
  cache gerektirirse.

## D-047 — Aidat ekranı dönem tahsilatını allocation bazında gösterir

- **Karar:** Organization admin aidat ekranındaki tahsilat, yalnız seçilen
  yıl/aya ait posted borçlara bağlı geçerli ödeme dağıtımlarının toplamıdır.
- **Gerekçe:** Ödeme en eski açık borçtan başladığında önceki ayı kapatan
  tutarın yanlışlıkla seçili ay tahsilatı olarak sunulmasını önlemek.
- **MVP kapsamı:** Aktif bina/dönem seçimi, toplu aidat oluşturma, daire
  durumları, PRG tabanlı ödeme girişi ve sade finans detayı.
- **Sonraya bırakılan alternatif:** Döneme özel manuel mahsup seçimi, gelişmiş
  raporlar ve resident görünümü.
- **Yeniden değerlendirme koşulu:** Kullanıcıların otomatik mahsup sırasını
  değiştirmesi veya raporlanabilir mahsup düzeltmesi gerekirse.

## D-048 — Ödeme allocation sırasında satır kilidi kullanır

- **Karar:** PostgreSQL'de payment ve açık charge sorguları transaction içinde
  `SELECT FOR UPDATE` ile kilitlenir; SQLite test ortamında desteklenen doğal
  fallback kullanılır.
- **Gerekçe:** Paralel ödeme dağıtımlarının payment veya charge limitini aşma
  riskini azaltmak ve payment/allocation işlemini atomik tutmak.
- **MVP kapsamı:** Tek uygulama transaction'ında ödeme kaydı, oldest-first
  allocation, rollback ve POST/Redirect/GET akışı.
- **Sonraya bırakılan alternatif:** Dağıtık kilit veya ayrı allocation kuyruğu.
- **Yeniden değerlendirme koşulu:** Yük testi yüksek contention ya da birden
  fazla yazma kaynağı gösterirse.

## D-049 — Resident finans görünümü read-only ve membership scoped'dur

- **Karar:** Resident finans route'ları yalnız aktif organization üyeliği ve
  dönemsel olarak geçerli ApartmentMembership ile erişilen aktif daire/bina
  kayıtlarını gösterir; hiçbir resident mutation route'u bulunmaz.
- **Gerekçe:** Daire geçmişini veya başka tenant verisini IDOR yoluyla ifşa
  etmeden resident deneyimini minimum ve güvenilir tutmak.
- **MVP kapsamı:** Çoklu daire seçimi, güncel borç, son ödemeler, hesap
  hareketleri ve kullanıcı dostu boş durum.
- **Sonraya bırakılan alternatif:** Geçmiş üyelik erişim politikası, resident
  ödeme işlemi, gider, duyuru ve belge ekranları.
- **Yeniden değerlendirme koşulu:** Hukuki geçmiş erişim veya online ödeme
  gereksinimi kesinleşirse.

## D-050 — Kullanılmamış ödeme borçtan ayrı gösterilir

- **Karar:** Güncel borç yalnız posted borçlar ile bunlara bağlı geçerli
  allocation'lardan hesaplanır. Henüz dağıtılmamış ödeme ayrı bilgi olarak
  gösterilir ve running debt balance değerini azaltmaz.
- **Gerekçe:** Yönetici mahsup yapmadan resident'a gerçekte kapanmamış borcu
  kapalı veya düşük göstermemek.
- **MVP kapsamı:** Payment hareketi ekstrede yalnız borçlara uygulanan kısmı
  kadar bakiye etkisi oluşturur; teknik allocation satırları gizlidir.
- **Sonraya bırakılan alternatif:** Resident'a mahsup detayı veya net
  alacak/borç görünümü sunmak.
- **Yeniden değerlendirme koşulu:** Ürün politikası kullanılmamış ödemenin
  otomatik mahsup edilmesini veya resident onayıyla dağıtılmasını gerektirirse.

## D-051 — Yapıbina Apsiyon'un yerine geçmez

- **Karar:** Apsiyon ana operasyon ve veri kaynağı olarak kalır. Yapıbina,
  aktarılan doğrulanmış veriyi sadeleştiren white-label read-model platformudur.
- **Gerekçe:** Malik/kiracı tarihçesi, muhasebe, banka ve tahsilat gibi kapsamlı
  operasyon kurallarını ikinci kez kurmadan dört temel kullanıcı değerine
  odaklanmak.
- **MVP kapsamı:** Borç/ödeme görünümü ile gider ve duyuru sunumuna uygun standart
  veri sözleşmesi.
- **Sonraya bırakılan alternatif:** Yapıbina'yı tam operasyon veya muhasebe
  sistemine dönüştürmek.
- **Yeniden değerlendirme koşulu:** Ürün misyonunun ticari olarak açık biçimde
  değiştirilmesi ve bunun için ayrı mimari onay verilmesi.

## D-052 — Kaynak adapter ile standart ara format ayrıdır

- **Karar:** Apsiyon raporları önce adapter tarafından Yapıbina standart Excel
  sözleşmesine normalize edilir; importer yalnız bu sözleşmeye bağlanır.
- **Gerekçe:** Kaynak kolon/rapor değişikliklerini uygulama ve importer
  çekirdeğinden izole etmek.
- **MVP kapsamı:** Sites, residents_and_units, charges, payments, expenses ve
  announcements veri kümeleri; stabil source key ve idempotent upsert anlamı.
- **Sonraya bırakılan alternatif:** Importer'ı doğrudan Apsiyon'un mevcut
  kolonlarına bağlamak.
- **Yeniden değerlendirme koşulu:** Yeni kaynak sistemler ortak formatın
  sürümlenmesini veya genişletilmesini gerektirirse.

## D-053 — Demo paketi deterministik ve manifest doğrulamalıdır

- **Karar:** Kurgusal demo Excel dosyaları sabit seed ve sabit metadata ile
  üretilir; manifest satır sayısı ve SHA-256 değerlerini taşır.
- **Gerekçe:** Ürün demosu, importer fixture'ı ve gelecekteki adapter sözleşmesi
  için tekrarlanabilir, değişikliği izlenebilir veri sağlamak.
- **MVP kapsamı:** Beş site, 50 bağımsız bölüm/resident, Şubat–Temmuz 2026,
  kontrollü finans senaryoları, giderler ve duyurular.
- **Sonraya bırakılan alternatif:** Elle düzenlenen veya rastgele her çalışmada
  değişen demo dosyaları.
- **Yeniden değerlendirme koşulu:** Schema version yükseldiğinde veya yeni demo
  senaryoları ürün kabul kriterine girdiğinde.

## D-054 — Importer merkezi external mapping kullanır

- **Karar:** Kaynak kimlikleri tenant, source system, entity type ve source key
  bileşimi benzersiz olan `ExternalRecordMap` ile iç UUID kayıtlarına eşlenir.
- **Gerekçe:** Domain tablolarını kaynağa özel kolonlarla kirletmeden birden
  fazla adapter ve tenant için idempotency sağlamak.
- **MVP kapsamı:** Site/building, unit/apartment, resident/user, charge ve
  payment eşlemeleri; mapping iç UUID'sinin polymorphic bütünlüğü service
  katmanında doğrulanır.
- **Sonraya bırakılan alternatif:** Her domain tablosuna source kolonları veya
  entity başına ayrı mapping tabloları eklemek.
- **Yeniden değerlendirme koşulu:** Polymorphic bütünlük hatası görülürse ya da
  entity-specific database foreign key zorunluluğu oluşursa.

## D-055 — Aynı paket fingerprint'i no-op'tur

- **Karar:** Manifestteki schema sürümü ile sıralı dosya/hash listesinden stabil
  fingerprint üretilir. Aynı tenant/source için tamamlanmış fingerprint yeniden
  gelirse yeni run veya domain kaydı oluşturulmadan `already_imported` döner.
- **Gerekçe:** Operasyonel tekrarların gözlenebilir, hızlı ve güvenli olması.
- **MVP kapsamı:** ImportRun durum/sayaçları, organization başına tek running
  import ve tamamlanan fingerprint için unique koruma.
- **Sonraya bırakılan alternatif:** Aynı paketi her seferinde satır satır tekrar
  işlemek.
- **Yeniden değerlendirme koşulu:** Aynı byte paketinin bilinçli reprocessing
  ihtiyacı doğarsa.

## D-056 — Finansal kritik import değişiklikleri reddedilir

- **Karar:** Aynı source key için charge/payment tutarı, daire, bina, tarih veya
  ödeme yöntemi sessizce değiştirilmez; import tamamen rollback edilir. Açıklama
  gibi güvenli alanlar güncellenebilir.
- **Gerekçe:** Allocation ve bakiye geçmişini geriye dönük bozmayı engellemek.
- **MVP kapsamı:** Append/upsert, no-delete; paketten artık gelmeyen kayıtlar
  silinmez veya pasifleştirilmez.
- **Sonraya bırakılan alternatif:** Kontrollü reversal ve yeniden hesaplama.
- **Yeniden değerlendirme koşulu:** Gerçek Apsiyon raporlarının düzeltme ve
  silinme semantiği doğrulandığında.

## D-057 — Import charge kayıtları yapay batch üretmez

- **Karar:** Standart pakette her charge kendi stabil source key'ine sahip
  olduğundan imported charge kayıtları nullable `charge_batch_id` ile doğrudan
  posted oluşturulur.
- **Gerekçe:** Yönetici tarafından oluşturulan toplu aidat batch semantiğini
  dış kaynak hareketleri için uydurma kayıtlarla karıştırmamak.
- **MVP kapsamı:** Mevcut manuel/toplu aidat akışına dokunmadan charge importu.
- **Sonraya bırakılan alternatif:** Adapter gerçek batch kimliği sağladığında
  deterministik imported batch eşlemesi.
- **Yeniden değerlendirme koşulu:** Kaynak sözleşmeye güvenilir batch anahtarı
  eklendiğinde.

## D-058 — Web import iki aşamalı ve fingerprint bağlıdır

- **Karar:** Organization admin web importu önce dry-run, sonra açık onay ile
  çalışır. Onay sunucu tarafında tenant, rastgele staging token ve fingerprint
  üçlüsüne bağlıdır.
- **Gerekçe:** Dosya değişimi, cross-tenant onay, yanlışlıkla import ve çift
  form gönderimi risklerini azaltmak.
- **MVP kapsamı:** Güvenli ZIP staging, CSRF, boyut/içerik/path doğrulaması,
  senkron import ve tenant-scoped geçmiş/detay.
- **Sonraya bırakılan alternatif:** Doğrudan upload sonrası import veya sahte
  progress gösteren request-içi işlem.
- **Yeniden değerlendirme koşulu:** Paket boyutu/request süresi background job
  ve kalıcı private object storage gerektirdiğinde.

## D-059 — Organization-level import yalnız organization admin yetkisidir

- **Karar:** Organization Import Center aktif tenant context ve
  `organization_admin_required` ister. Building manager, resident ve platform
  admin tenant yetkisini otomatik kazanmaz.
- **Gerekçe:** Import bütün organization kapsamını ve finansal read-model
  verisini değiştirebilir; bina düzeyi yetki yeterli değildir.
- **MVP kapsamı:** Tenant dışı ImportRun için 404, rol yetersizliğinde 403.
- **Sonraya bırakılan alternatif:** Açık organization-level import permission
  veya süreli platform break-glass erişimi.
- **Yeniden değerlendirme koşulu:** Ayrıntılı permission modeli veya onay
  workflow'u eklendiğinde.

## D-060 — Dashboard finans metrikleri read-model sorgularıdır

- **Karar:** Organization dashboard metrikleri kalıcı sayaç/cache alanlarında
  değil tenant-scoped aggregate sorgulardan üretilir.
- **Gerekçe:** Finansal doğruluk kaynağını Charge, Payment ve
  PaymentAllocation kayıtlarında tutmak; güncelliğini yitiren özet kolonlarından
  kaçınmak.
- **MVP kapsamı:** Açık borç posted charge eksi geçerli allocation; aylık
  tahakkuk period alanları veya fallback due_date; aylık tahsilat posted payment
  tarihi; Decimal tahsilat oranı.
- **Sonraya bırakılan alternatif:** Materialized view, projection veya cache.
- **Yeniden değerlendirme koşulu:** Production ölçümleri aggregate sorguların
  kabul edilen yanıt süresini aşmasını gösterirse.

## D-061 — Dashboard yalnız organization admin görünümüdür

- **Karar:** Genel Bakış aktif tenant context ve organization admin rolü ister;
  platform admin, building manager, organization member ve resident otomatik
  erişim kazanmaz.
- **Gerekçe:** Dashboard tüm organization'ın finans ve resident özetlerini
  içerir; bina veya daire düzeyi yetki yeterli değildir.
- **MVP kapsamı:** Organization seçimi URL/formdan alınmaz, her sorgu açık
  organization scope taşır ve başka tenant verisi birleşik hareketlere girmez.
- **Sonraya bırakılan alternatif:** Building manager için yalnız atanmış
  binaları içeren ayrı dashboard.
- **Yeniden değerlendirme koşulu:** Organization-level ayrıntılı permission
  modeli devreye alındığında.

## D-062 — Bina listesi toplu read-model sorgusudur

- **Karar:** Organization bina listesi, tenant filtreli aggregate alt sorguları
  birleştiren bir read-model servisiyle üretilir; satır başına sorgu çalışmaz.
- **Gerekçe:** Daire, resident ve finans metriklerini N+1 oluşturmadan aramak,
  sıralamak ve sayfalamak gerekir.
- **MVP kapsamı:** Filtrelenmiş toplam için bir count ve sayfa verisi için bir
  aggregate sorgu; ad, daire, açık borç ve aylık tahsilat için allowlist
  sıralama; 20/50/100 kayıtlık server-side sayfalama.
- **Sonraya bırakılan alternatif:** Cache, materialized view veya ayrı arama
  altyapısı.
- **Yeniden değerlendirme koşulu:** Production sorgu planları ve ölçümleri
  mevcut iki sorgulu yaklaşımın hedef yanıt süresini karşılamadığını gösterirse.

## D-063 — Bina listesi metrikleri dashboard ile aynı semantiği kullanır

- **Karar:** Açık borç, aylık tahsilat ve aktif resident tanımları Organization
  Dashboard ile ortak helper ve aynı filtre kurallarını kullanır.
- **Gerekçe:** Aynı tenant verisinin iki yönetim ekranında farklı toplamlarla
  görünmesi güven kaybı yaratır.
- **MVP kapsamı:** Posted charge eksi geçerli allocation, tekil posted payment
  aylık toplamı ve aktif user/organization/apartment üyeliği zinciri; tümünde
  açık `organization_id` kapsamı.
- **Sonraya bırakılan alternatif:** Kalıcı projection/snapshot metrikleri.
- **Yeniden değerlendirme koşulu:** Import edilen kaynak verinin finans veya
  resident semantiği değişirse ortak read-model kuralları birlikte güncellenir.

## D-064 — Bina detayı tenant-scoped read-model'dir

- **Karar:** Bina detayı `building_id` ile birlikte zorunlu
  `organization_id` filtresi kullanan, organization admin'e özel bir read-model
  servisidir.
- **Gerekçe:** Bina, daire, resident ve finans bilgilerinin UUID üzerinden
  tenant sınırı dışına sızmasını önlemek ve route/template katmanını hesap
  mantığından ayırmak.
- **MVP kapsamı:** Bina özeti, server-side daire arama/sıralama/sayfalama ve son
  on posted finans hareketi; başka tenant kaynağı için 404.
- **Sonraya bırakılan alternatif:** Building manager'a atanmış bina kapsamlı
  görünüm ve ayrı Apartment Detail ekranı.
- **Yeniden değerlendirme koşulu:** Organization-level permission modeli veya
  building manager ürün kapsamı genişletildiğinde.

## D-065 — Son ödeme daireye doğrudan bağlı posted payment'tır

- **Karar:** Daire satırındaki son ödeme, `Payment.apartment_id` üzerinden
  doğrudan bağlı en yeni posted payment; eşit tarihte `created_at` ve UUID ile
  deterministik seçilen kayıttır.
- **Gerekçe:** Mevcut model payment'ın bina ve daire ilişkisini doğrudan ve
  tenant-aware foreign keylerle taşır; allocation üzerinden dolaylı çıkarım
  gereksiz ve farklı borçlara dağıtımda yanıltıcıdır.
- **MVP kapsamı:** Tarih ve tutar gösterilir; unallocated kısım son ödeme
  kaydını değiştirmez ve açık borcu azaltmaz.
- **Sonraya bırakılan alternatif:** Allocation bazlı “borca uygulanan son
  ödeme” metriği.
- **Yeniden değerlendirme koşulu:** Gelecekte bir payment'ın birden fazla
  apartment'a dağıtılmasına izin veren model kabul edilirse.

## D-066 — Finans tarih ve dönem kuralları ortak helper'da tutulur

- **Karar:** Europe/Istanbul yerel gün/ay sınırı, charge dönem fallback'i ve
  Decimal normalizasyonu `finance_metrics` modülünde ortaklaştırılır.
- **Gerekçe:** Dashboard, bina listesi ve bina detayında aynı metriğin farklı
  yorumlanmasını önlemek.
- **MVP kapsamı:** Posted charge/payment ve geçerli allocation kullanan
  read-model sorguları; cache veya projection yoktur.
- **Sonraya bırakılan alternatif:** Ayrı finans projection servisi.
- **Yeniden değerlendirme koşulu:** Sorgu hacmi kalıcı özet/projection
  gerektirdiğinde.

## D-067 — Web ve mobil ortak application service kullanır

- **Karar:** Server-rendered web route'ları ve gelecekteki mobil API route'ları
  aynı domain/application service ve authorization policy katmanını kullanır;
  route'lar yalnız taşıma/presentation katmanıdır.
- **Gerekçe:** İş kurallarının web ve mobil için çatallanmasını, farklı tenant
  veya finans davranışları oluşmasını önlemek.
- **MVP kapsamı:** Service katmanı Flask request/session/flash/form/Jinja
  nesnelerinden bağımsız kalır; mevcut API yoktur.
- **Sonraya bırakılan alternatif:** Mobil için ayrı backend/BFF.
- **Yeniden değerlendirme koşulu:** Ölçülmüş istemci ihtiyaçları ayrı bir BFF
  gerektirirse, ortak domain use-case'leri korunarak değerlendirilir.

## D-068 — Gelecekteki API `/api/v1` ve ayrı authentication kullanır

- **Karar:** JSON API `/api/v1` ile sürümlenir. Authentication web session
  cookie'sinden ayrı bir adapter/protokol olarak tasarlanır; token türü bu
  aşamada seçilmez.
- **Gerekçe:** Mobil token yaşam döngüsü, revocation ve cihaz session'ları web
  cookie güvenlik modelinden farklıdır.
- **MVP kapsamı:** API blueprint, token veya OAuth/JWT implementasyonu yoktur.
- **Sonraya bırakılan alternatif:** Session cookie'yi mobilde paylaşmak veya
  sürümsüz endpoint.
- **Yeniden değerlendirme koşulu:** Mobil istemci authentication threat model'i
  ve operasyonel gereksinimleri onaylandığında.

## D-069 — API tenant kimliği istemci seçimi değildir

- **Karar:** `organization_id` istemciden serbest tenant seçimi olarak kabul
  edilmez. Tenant; doğrulanmış kullanıcı, aktif membership, kaynak scope'u ve
  gerektiğinde doğrulanmış host bağlamından çözülür.
- **Gerekçe:** Header/query/body manipülasyonu ile cross-tenant erişimi ve IDOR
  riskini önlemek.
- **MVP kapsamı:** Stabil UUID yalnız kaynak kimliğidir; her sorgu ayrıca açık
  organization ve authorization scope'u taşır.
- **Sonraya bırakılan alternatif:** Güvenilen entegrasyon istemcileri için açık
  tenant claim'i; yalnız imzalı ve server-side doğrulanmış protokolle.
- **Yeniden değerlendirme koşulu:** Service account veya partner API kapsamı
  tanımlandığında.

## D-070 — API serialization ve pagination sözleşmesi sabittir

- **Karar:** Para decimal string, tarih/tarih-saat ISO 8601 ve timezone bilgili,
  kimlik UUID string olarak taşınır. Sayfa tabanlı listeler ortak
  `page/per_page/total/pages/has_next/has_previous` metadata'sını ve tutarlı
  hata gövdesini kullanır.
- **Gerekçe:** Float hassasiyet kaybını, naive datetime belirsizliğini ve her
  mobil ekranda farklı pagination/hata yorumunu önlemek.
- **MVP kapsamı:** Bu kurallar belgelidir; JSON serializer/endpoint henüz yoktur.
- **Sonraya bırakılan alternatif:** Cursor pagination ve farklı wire format.
- **Yeniden değerlendirme koşulu:** Büyük, hızla değişen listelerde offset
  pagination ölçülmüş tutarlılık veya performans sorunu yaratırsa.

## D-071 — Announcement, Notification ve push ayrı yaşam döngüleridir

- **Karar:** Announcement kalıcı hedeflenebilir içerik; Notification kullanıcıya
  özgü teslim/okunma kaydı; push ise notification'dan bağımsız asenkron teslim
  altyapısıdır.
- **Gerekçe:** Push provider hatasının içerik transaction'ını geri almasını,
  okundu durumuyla harici teslim durumunun karışmasını önlemek.
- **MVP kapsamı:** Gelecekte bir announcement çok sayıda notification
  üretebilir. Push transactional outbox/background worker ile gönderilir;
  kullanıcı-cihaz token'ları iptal ve invalid-token temizliği taşır. Bu aşamada
  model, migration, worker veya provider yoktur.
- **Sonraya bırakılan alternatif:** Transaction içinde senkron push veya
  announcement satırında kullanıcı okundu alanları.
- **Yeniden değerlendirme koşulu:** Bildirim kanalları ve teslim SLA'sı
  kesinleştiğinde outbox retry/dead-letter ve token retention politikaları
  ayrıca kararlaştırılır.

## D-072 — Daire bakiye hareketinde yalnız allocation ödeme etkisi yaratır

- **Karar:** Apartment Detail running balance hareketlerinde posted charge
  borcu artırır; yalnız posted payment ile posted charge arasındaki geçerli
  `PaymentAllocation` borcu azaltır. Allocation zamanı, modeldeki timezone-aware
  `PaymentAllocation.created_at` alanıdır.
- **Gerekçe:** Payment'ın tahsis edilmemiş kısmını borçtan yanlışlıkla düşmemek
  ve gerçek borca uygulama anını deterministik biçimde göstermek.
- **MVP kapsamı:** Hareketler kronolojik `(occurred_at, tür, UUID)` sırasıyla
  hesaplanır; ekranda yeni→eski sunulsa da her satırın running balance değeri
  kronolojik hesaplamadan gelir. Son bakiye açık borçla eşittir.
- **Sonraya bırakılan alternatif:** Kaynak sistem allocation efektif tarihi
  veya ayrı finans event zamanı.
- **Yeniden değerlendirme koşulu:** Standart veri sözleşmesi güvenilir
  allocation efektif tarihi sağlamaya başladığında.

## Kodlamadan önce kalan kararlar

Aşağıdakiler uygulanmadan önce sahip ve tarih atanarak karara bağlanmalıdır:

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
