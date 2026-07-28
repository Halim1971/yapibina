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
