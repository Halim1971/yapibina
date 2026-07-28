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
