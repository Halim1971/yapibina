# Değişiklik Günlüğü

Bu proje Semantic Versioning yaklaşımını izleyecektir.

## [Unreleased]

### Eklendi

- Flask application factory tabanlı temel proje iskeleti
- Ortam yapılandırmaları, extension nesneleri ve blueprint sınırları
- Health endpoint'i, merkezi hata yönetimi ve tenant çözümleme arayüzü
- Varsayılan tema, test ve kod kalitesi yapılandırmaları
- UUID tabanlı User, Organization, Branding, Domain, Building ve Apartment modelleri
- Organization, building ve tarihsel apartment membership modelleri
- Cross-tenant ilişki kontrolleri sağlayan temel service katmanı
- Aktif domain ve aktif organization sorgusuna bağlı tenant resolver
- Taşınabilir string enum ve PostgreSQL/SQLite uyumlu constraint/index yaklaşımı
- Tenant çekirdek tablolarını oluşturan ilk Alembic migration'ı
- Tenant-domain-membership uyumlu güvenli login ve POST-only logout
- CSRF koruması, güvenli cookie/session ayarları ve open redirect kontrolü
- Minimum parola politikası ve IP tabanlı login rate limit
- Kaynak kapsamlı authorization policy/decorator'ları
- Session sonrası user, organization ve membership yetkisi yeniden doğrulaması
- Platform organization, branding, domain ve organization admin yönetimi
- Tenant-scoped bina, daire, kullanıcı ve üyelik yönetim ekranları
- Domain state transition servisi ve yönetim listelerinde sayfalama/arama
- Decimal tabanlı ChargeBatch, Charge, Payment ve PaymentAllocation modelleri
- Atomik aidat posting, manuel borç, ödeme, allocation ve oldest-first otomatik mahsup servisleri
- Finansal reversal/immutability, tenant scope ve sorgudan hesaplanan bakiye kuralları
- Aidat ve ödeme çekirdeği için Alembic migration'ı
- Organization admin için bina/dönem filtreli aidat takip ekranı
- Aktif dairelere tek akışta toplu aidat oluşturma ve PRG tabanlı ödeme girişi
- Seçili dönem allocation'larından hesaplanan tahsilat ve sade daire finans detayı
- Aktif daire üyeliğiyle sınırlı read-only resident finans ekranları
- Resident güncel borç, son ödemeler, hesap ekstresi ve ayrı kullanılmamış ödeme özeti
- Çoklu daire seçimi, running balance ve resident finans pagination desteği
- Adapter-bağımsız standart Excel veri sözleşmesi ve deterministik demo paketi
- Beş site, 50 daire/resident ve kontrollü altı aylık finans senaryoları
- Manifest satır/hash doğrulamalı demo generator ve validator araçları
- Tenant-aware, transaction-safe ve idempotent standart Excel importer
- Import run/fingerprint takibi ve merkezi dış kaynak anahtarı eşleme modeli
- Doğrulama ve dry-run destekli `flask import-standard-data` komutu
- Organization admin için dry-run → açık onay akışlı Veri İçe Aktarma merkezi
- Tenant-scoped import geçmişi/detayı ve güvenli geçici ZIP paket işleme
- Organization admin için tenant-scoped operasyon ve finans genel bakış ekranı
- Toplu sorgularla bina özeti, son import durumu ve birleşik finans hareketleri
- Tenant-scoped arama, allowlist sıralama ve server-side sayfalama kullanan bina listesi
- Bina bazında daire, aktif resident, açık borç ve aylık tahsilat özetleri
- Organization admin için tenant-scoped bina detay ve daire özet ekranı
- Daire/resident araması, aggregate sıralama, sayfalama ve son finans hareketleri
