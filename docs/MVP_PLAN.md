# Yapıbina MVP Geliştirme Planı

## 1. MVP tanımı

MVP; tek production ortamında birden fazla organization'ı güvenli biçimde barındıran, her organization'a geçici Yapıbina alt alan adı sağlayan ve resident'a yalnız şu dört işlevi sunan kullanılabilir üründür:

1. Daire ekstresi
2. Bina banka hareketleri
3. Gider ve belgeleri
4. Duyurular

Organization admin ve building manager, bu dört işlev için gerekli asgari yönetim operasyonlarını yapabilir. Özel domain akışı production güvenliğiyle desteklenir.

## 2. Fazlar

### Faz 0 — Kararların kesinleştirilmesi

Amaç: Belirsiz iş kurallarını koddan önce kapatmak.

Teslimatlar:

- Onaylanmış mimari belgeler ve karar kayıtları
- Onaylanmış aktif-membership resident erişim politikası
- Tahakkuk, ödeme, allocation, ters kayıt ve dönem kuralları
- Kontrollü manuel domain/SSL operasyon runbook'u
- PDF/JPG/JPEG/PNG, 10 MB ve otomatik silmesiz dosya politikası

Kabul kriterleri:

- Kodlamayı etkileyen kalan kararların sahibi ve hedef tarihi vardır.
- MVP dışı talepler ayrı backlog'dadır.
- Tenant güvenlik invariants test edilebilir cümlelerle yazılmıştır.

### Faz 1 — Proje temeli ve kalite kapıları

Amaç: Tekrarlanabilir, test edilebilir uygulama iskeleti.

Teslimatlar:

- Flask application factory ve environment ayrımı
- Bağımlılık ve yapılandırma yönetimi
- Test altyapısı, lint/format/type politikası
- Güvenli secret ve loglama temeli
- CI kalite kapıları

Kabul kriterleri:

- Uygulama development/test yapılandırmalarıyla factory üzerinden açılır.
- Secret yokluğunda güvenli biçimde başarısız olur.
- Otomatik test komutu temiz ortamda tekrarlanabilir çalışır.

### Faz 2 — Tenant, domain, kimlik ve roller

Amaç: İzolasyonun ürün işlevlerinden önce kurulması.

Teslimatlar:

- Organization/domain/user/membership/building/apartment çekirdeği
- Host allowlist, tenant resolution ve tenant context
- Flask-Login, session ve CSRF
- Dört rolün policy'leri
- Platform ve tenant temel ekran akışları

Kabul kriterleri:

- Bilinmeyen/pasif host reddedilir.
- Yanlış organization kullanıcısı doğru parolayla giriş yapamaz.
- Çapraz tenant ID testleri okuma ve yazmada başarısız olur.
- Manager yalnız atanmış binaya erişir.
- Resident yalnız aktif membership bulunan daire/bina verisini görür; sona ermiş ilişki erişim vermez.
- Platform super admin production MFA akışı test edilir.
- Membership pasifleştirme geçmiş kaydı silmez ve mevcut erişimi keser.

### Faz 3 — Daire ekstresi

Amaç: Güvenilir minimum finansal ledger.

Teslimatlar:

- `aidat/ek_borc/duzeltme/diger` tahakkukları; zorunlu vade ve isteğe bağlı dönem
- Manuel ve toplu tahakkuk; otomatik tekrarlama/faiz/ceza yok
- Kısmi ödeme, çoklu borca allocation, dağıtılmamış kredi ve ters kayıt
- Daire ekstresi ve güncel bakiye
- Decimal/Numeric para işleme
- Kritik audit kayıtları

Kabul kriterleri:

- Bakiye deterministik olarak ledger'dan yeniden hesaplanır.
- Posted kayıt güncellenemez/silinemez.
- Ters kayıt orijinal etkiyi doğru sıfırlar.
- Varsayılan allocation en eski vadesi geçmiş/açık borç sırasını izler.
- Allocation toplamı ödeme ve borç sınırlarını service ve DB seviyesinde aşamaz.
- Mükerrer form gönderimi çift finansal kayıt üretmez.
- Para ve tarih Türkiye biçiminde gösterilir.

### Faz 4 — Banka hareketleri ve import

Amaç: Şeffaf banka görünümü ve güvenli veri alımı.

Teslimatlar:

- Manuel giriş
- En az bir tanımlı CSV ve gerekliyse Excel şablonu
- Önizleme/doğrulama/import sonucu
- Mükerrerlik fingerprint/idempotency kontrolü

Kabul kriterleri:

- Hatalı satırlar import öncesi açıkça gösterilir.
- Import transaction davranışı tanımlıdır; kısmi/tam başarısızlık testlidir.
- CSV formula injection ve tehlikeli hücre içerikleri güvenli ele alınır.
- Resident yalnız kendi binasının hareketlerini okur.

### Faz 5 — Gider ve belge yönetimi

Amaç: Gider ile kanıt belgesini güvenli ve görünür kılmak.

Teslimatlar:

- Kategori ve gider CRUD/iptal akışı
- Banka hareketi eşleştirme
- Storage portu ve yerel private adapter
- Yetkili yükleme/indirme, doğrulama, audit

Kabul kriterleri:

- Dosya yolu iş mantığında bulunmaz.
- Yetkisiz ve çapraz tenant indirme engellenir.
- Boyut, MIME, uzantı ve güvenli ad kontrolleri çalışır.
- Arşivlenmiş/rejected belge resident'a sunulmaz.
- Yalnız PDF/JPG/JPEG/PNG ve en fazla 10 MB kabul edilir.
- İndirme yalnız yetkili Flask endpoint'inden yapılır.
- Harici antivirüs olmadan hook/adapter sınırı korunur; otomatik silme yapılmaz.

### Faz 6 — Duyurular ve resident deneyimi

Amaç: Dört menülü sade, mobil öncelikli resident ürünü.

Teslimatlar:

- Taslak/yayın/geçerlilik akışı
- Okundu bilgisi
- Ekstrem/Banka/Giderler/Duyurular navigasyonu
- Organization branding fallback sistemi

Kabul kriterleri:

- Resident görünümünde yalnız dört ana menü vardır.
- Geçerlilik dışındaki duyuru varsayılan listede görünmez.
- Tema eksik/bozuksa Yapıbina varsayılanları kullanılır.
- Temel akışlar mobil ve masaüstü functional testlerden geçer.

### Faz 7 — Özel domain ve production hazırlığı

Amaç: İlk güvenli müşteri yayını.

Teslimatlar:

- DNS doğrulama ve domain yaşam döngüsü
- Kontrollü manuel DNS, Certbot ve Nginx config test/reload operasyonu
- Gunicorn/systemd deployment
- Yedekleme, geri yükleme, health, log rotation, hata takibi
- Runbook ve geri alma planı

Kabul kriterleri:

- Geçici ve özel domain aynı tenant'ı güvenli çözer.
- Domain state geçişleri `pending → awaiting_dns → dns_verified → ssl_pending → active`; hata/suspend geçişleri kontrollüdür.
- Sertifikası hazır olmayan domain aktif olmaz.
- Nginx configuration testi başarısızsa reload ve aktivasyon yapılmaz; mevcut müşteriler etkilenmez.
- PostgreSQL ve dosya yedeği alınır ve staging'e geri yüklenir.
- Günlük DB/dosya yedeğinin en az bir şifreli off-site kopyası vardır; başlangıç RPO 24 saat ve RTO 4 saat prova edilir.
- Deployment sonrası smoke test ve rollback provası yapılır.
- Kritik güvenlik ve tenant izolasyon testleri yeşildir.

### Faz 8 — Kontrollü pilot

Amaç: Tek örnek müşteriye hard-code etmeden gerçek kullanım doğrulaması.

Teslimatlar:

- Sınırlı pilot organization
- İzleme, destek ve geri bildirim kaydı
- Performans/güvenlik bulguları

Kabul kriterleri:

- Kritik veri izolasyonu veya finansal doğruluk hatası yoktur.
- Dört resident görevi eğitim gerektirmeden tamamlanabilir.
- Operasyon ekibi yedek, domain ve rollback runbook'unu uygulayabilir.

## 3. MVP kapsamı

- Organization, domain, branding
- Dört rol ve çoklu membership
- Bina, daire ve sakin yönetimi
- Basit append-only daire ledger'ı
- Manuel ve CSV/Excel banka hareketi
- Gider, kategori, belge ve banka eşleştirmesi
- Duyuru ve okundu kaydı
- Audit, tenant izolasyonu, güvenli dosya erişimi
- Geçici alt domain ve özel müşteri alt domaini
- Türkçe, TRY, Europe/Istanbul sunumu
- Ubuntu/Nginx/Gunicorn/PostgreSQL production
- Platform super admin için zorunlu MFA ve audit'li break-glass destek erişimi

## 4. MVP dışı

- Doğrudan banka API entegrasyonu
- Genel muhasebe / çift taraflı muhasebe ürünü
- Bordro, CRM, satın alma, stok, e-fatura
- Path tabanlı tenant (`/panel`)
- Native mobil uygulama
- Web Push (mimari hazırlık dışında)
- Çok dil/çok para birimi iş akışları
- Her tenant için ayrı veritabanı
- Sınırsız tema/template özelleştirmesi
- Gelişmiş otomatik banka-gider mutabakatı
- Kısmi/bölünmüş/çoklu banka-gider mutabakatı
- Otomatik tekrarlayan aidat ve gecikme faizi/cezası

## 5. Test stratejisi

- Unit: ledger hesapları, policy'ler, hostname normalizasyonu, tema fallback, parser'lar.
- Integration: PostgreSQL constraint'leri, repository tenant filtreleri, transaction ve storage adapter.
- Functional: rol bazlı HTTP akışları, CSRF, giriş, dört resident görevi.
- Security: çapraz tenant matris testleri, IDOR, host spoofing, upload, session ve rate limit.
- Migration: boş veritabanına ileri migration ve desteklenen geri alma/restore stratejisi.
- Backup/restore: gerçekçi veri ve dosyalarla düzenli prova.
- Performance: büyük ekstre, banka listesi ve audit hacmi için hedef sorgu bütçeleri.

Her yeni tenant tablosu için aynı organization'da başarılı ve farklı organization'da başarısız erişim testleri zorunlu kalite kapısıdır.

## 6. Teknik borçtan kaçınma kuralları

- Route içinde iş kuralı veya doğrudan model sorgusu yazılmaz.
- Tenant-scoped `find_by_id` metodu oluşturulmaz.
- Para `float` kullanılmaz.
- Posted ledger/audit fiziksel olarak silinmez.
- Dosya yolları service/model içine gömülmez.
- Müşteri adına özel template, CSS veya koşul eklenmez.
- Secret kodda, repoda veya logda tutulmaz.
- Migration atlanarak manuel production schema değişikliği yapılmaz.
- Testi olmayan yetki değişikliği birleştirilmez.
- MVP dışı kapsam mimari çekirdeğe sızdırılmaz.

## 7. Riskler ve azaltımlar

| Risk | Azaltım |
|---|---|
| Tenant veri sızıntısı | Merkezî context, scoped repository, birleşik FK, negatif güvenlik testleri |
| Finansal yanlışlık | Decimal, append-only ledger, idempotency, audit, reconciliation testleri |
| Domain/SSL operasyon hatası | Durum makinesi, kontrollü manuel runbook, config test ve atomik reload |
| Zararlı dosya | Private storage, tür/MIME allowlist, 10 MB sınır, tarama hook'u |
| Import veri kalitesi | Önizleme, açık format, satır doğrulama, fingerprint |
| Kapsam büyümesi | Dört işlev ilkesi ve açık MVP dışı backlog |
| Tek VPS arızası | Offsite şifreli yedek, restore testi, izleme; ölçek büyüyünce HA |
| Yetersiz audit | Kritik use-case checklist'i ve entegrasyon testleri |

## 8. İlk production'a kadar sıra

Kararların kapanması → proje temeli → tenant/kimlik/yetki → ledger → banka → gider/storage → duyuru/UI → özel domain → operasyon güvenliği → staging kabul → yedek/rollback provası → pilot production.

## 9. Kesinleşen operasyon hedefleri ve kalan kararlar

- Pilot müşteri sayısı ve veri hacmi henüz bilinmiyor.
- Excel desteğinin MVP zorunluluğu ve kütüphane güvenlik değerlendirmesi netleşmeli.
- Harici antivirüs MVP'de zorunlu değildir; entegrasyon hook'u bulunur.
- Domain onboarding MVP'de kontrollü manuel operasyondur; tam otomasyon sonraya bırakılmıştır.
- Günlük DB ve dosya yedeği, şifreli off-site kopya, RPO 24 saat ve RTO 4 saat kabul edilmiştir.
- Kesin backup retention gün/hafta/ay değerleri production operasyon planında belirlenmelidir.
- Tek Ubuntu VPS ilk müşteriler için kabul edilmiştir ve açık bir single point of failure'dır; Kubernetes kurulmaz.
