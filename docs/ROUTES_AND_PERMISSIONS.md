# Route ve Yetki Mimarisi

## 1. İlkeler

- URL'deki kaynak ID'si hiçbir zaman tek başına erişim kanıtı değildir.
- Organization, doğrulanmış hosttan çözülür; form, query string veya session tenant'ın doğruluk kaynağı değildir.
- Her route kimlik doğrulama, rol, membership, kaynak kapsamı ve işlem iznini ayrı ayrı kontrol eder.
- Yetkisiz erişim varsayılan olarak reddedilir.
- Resident yazma işlemi yapamaz; yalnız duyuru okundu kaydı kullanıcı eylemi olarak oluşturulabilir.

## 2. Blueprint ve URL alanları

| Blueprint | Önerilen prefix | Amaç |
|---|---|---|
| `auth` | `/auth` | tenant hostunda giriş/çıkış |
| `platform` | `/platform` | merkezi hostta platform yönetimi |
| `organization` | `/organization` | organization yetki placeholder'ı |
| `building` | `/manage` | bina operasyonları |
| `resident` | `/` | resident'ın dört ana görünümü |

Rol bazlı ayrı prefix'ler URL çakışmasını ve zihinsel karmaşayı azaltır. Aynı service gerektiğinde farklı blueprint'lerden çağrılabilir.

## 3. Tenant çözümleme akışı

1. Nginx orijinal hostname'i iletir.
2. Uygulama hostu normalize eder.
3. Merkezi platform hostu ise yalnız platform route'ları değerlendirilir.
4. Müşteri hostu ise aktif, doğrulanmış domain ve aktif organization aranır.
5. Tenant context kurulur.
6. Oturum kullanıcısının tenant üyeliği doğrulanır.
7. Route-specific policy çalışır.

Bilinmeyen host `421 Misdirected Request` veya markasız güvenli `404` ile reddedilmelidir. Merkezi sayfaya yönlendirme seçilirse hedef sabittir; kullanıcı hostundan URL türetilmez.

## 4. Kimlik doğrulama route'ları

| Yöntem ve route | Roller | Kontrol |
|---|---|---|
| `GET/POST /auth/login` | anonim | Host tenant olmalı; kullanıcı bu tenant'a bağlı olmalı |
| `POST /auth/logout` | tüm authenticated | CSRF |
Parola sıfırlama route'ları henüz uygulanmamıştır.

### Uygulanan login güvenlik davranışı

- Tenant hostunda aktif user + aktif organization + geçerli aktif
  OrganizationMembership birlikte aranır.
- Platform hostunda yalnız aktif platform super admin kabul edilir.
- Başarısız credential/tenant/member kontrolleri aynı genel mesajı üretir.
- Login ve POST-only logout CSRF korumalıdır.
- Güvenli relative `next` kabul edilir; harici veya `//` hedefler varsayılan rol
  hedefine düşer.
- Hedef önceliği platform → organization/building görevi → resident erişimidir.
- Tenant dışı building/apartment IDOR denemesi 404, tenant içi yetersiz rol 403
  üretir.

Yanlış organization domaininde geçerli e-posta/parola kullanılması giriş sağlamaz. Kullanıcıya başka müşteride hesabı bulunduğu açıklanmaz.

## 5. Platform super admin

Yalnız merkezi platform hostu ve `platform_super_admin`.

| Yöntem ve route | Amaç |
|---|---|
| `GET /platform/organizations` | Organization listesi |
| `GET/POST /platform/organizations/new` | Organization oluşturma |
| `GET /platform/organizations/<organization_id>` | Detay |
| `POST /platform/organizations/<organization_id>/status` | Aktif/pasif/suspend |
| `GET/POST /platform/organizations/<organization_id>/domains` | Domain yönetimi |
| `POST /platform/domains/<domain_id>/verify` | Manuel DNS kontrolü ve `dns_verified` geçişi |
| `POST /platform/domains/<domain_id>/ssl-ready` | Certbot sonrası SSL-ready kaydı |
| `POST /platform/domains/<domain_id>/activate` | Nginx config testi/reload sonrası aktivasyon |
| `POST /platform/domains/<domain_id>/suspend` | Domain pasifleştirme |
| `GET /platform/operations/health` | Platform sorun görünümü |
| `GET /platform/audit` | Yetkili platform audit görünümü |

Paket/kullanım route'ları ürün modeli netleşince eklenir; MVP'ye varsayılan abonelik sistemi eklenmez.

## 6. Organization admin

Aktif `organization_membership(role=organization_admin)` gerekir.

| Yöntem ve route | Amaç |
|---|---|
| `GET /organization/dashboard` | Organization özeti |
| `GET/POST /organization/settings` | Firma ayarları |
| `GET/POST /organization/branding` | Tema ve marka |
| `GET /organization/users` | Firma kullanıcıları |
| `GET/POST /organization/users/invite` | Kullanıcı daveti |
| `POST /organization/users/<user_id>/status` | Üyelik durumu |
| `GET /organization/buildings` | Binalar |
| `GET/POST /organization/buildings/new` | Bina oluşturma |
| `GET/POST /organization/buildings/<building_id>` | Bina görüntüleme/düzenleme |
| `GET/POST /organization/buildings/<building_id>/managers` | Manager atama |
| `POST /organization/apartment-memberships/<membership_id>/status` | Sakin üyeliğini aktif/pasif yapma |

Organization admin, kendi organization'ındaki bina operasyon route'larına da policy kararıyla erişebilir. Bu karar açıkça tanımlanmalı ve test edilmelidir.

## 7. Building manager

Hedef bina için aktif `building_membership(role=building_manager)` veya organization admin yetkisi gerekir.

| Yöntem ve route | Amaç |
|---|---|
| `GET /manage/buildings` | Yetkili binalar |
| `GET /manage/buildings/<building_id>` | Bina operasyon özeti |
| `GET/POST /manage/buildings/<building_id>/apartments` | Daire yönetimi |
| `GET/POST /manage/apartments/<apartment_id>/residents` | Sakin üyelikleri |
| `POST /manage/apartment-memberships/<membership_id>/status` | Yetkili binada üyeliği aktif/pasif yapma |
| `GET /manage/apartments/<apartment_id>/ledger` | Ekstre |
| `POST /manage/apartments/<apartment_id>/ledger/charges` | Tahakkuk/ek borç |
| `POST /manage/buildings/<building_id>/ledger/charges/bulk` | Toplu tahakkuk |
| `POST /manage/apartments/<apartment_id>/ledger/payments` | Ödeme |
| `POST /manage/payments/<payment_id>/allocations` | Ödeme dağıtımını kesinleştirme |
| `POST /manage/charges/<charge_id>/reverse` | Borç ters kaydı |
| `POST /manage/payments/<payment_id>/reverse` | Ödeme ters kaydı |
| `GET/POST /manage/buildings/<building_id>/bank-transactions` | Manuel banka hareketi |
| `GET/POST /manage/buildings/<building_id>/bank-imports` | Import |
| `GET/POST /manage/buildings/<building_id>/expenses` | Gider |
| `POST /manage/expenses/<expense_id>/documents` | Belge yükleme |
| `GET/POST /manage/buildings/<building_id>/announcements` | Duyuru |
| `POST /manage/announcements/<announcement_id>/publish` | Yayınlama |

Finansal POST işlemlerinde idempotency/yeniden gönderim koruması ve audit zorunludur. Kısmi ödeme ile birden çok borca allocation desteklenir; varsayılan öneri en eski vadesi geçmiş/açık borç sırasıdır. Üyelik status değişikliği geçmiş satırı silmez.

## 8. Resident

Uygulanan resident finans route'ları salt okunur ve tenant hostname gerektirir:

| Route | İşlev |
|---|---|
| `GET /resident/` | Borç, son ödeme, kullanılmamış ödeme ve son hareket özeti |
| `GET /resident/account` | Eskiden yeniye hesap hareketleri ve running balance |
| `GET /resident/payments` | Geçerli ödeme geçmişi |
| `GET /resident/transactions` | Hesap hareketlerine uyumluluk yönlendirmesi |

Seçim gerekiyorsa `apartment_id` query parametresi yalnız aktif
ApartmentMembership kapsamındaki dairelerle doğrulanır. Aktif organization
membership, user, building ve apartment koşulları da zorunludur. Organization
admin, building manager veya platform admin rolü kendiliğinden resident erişimi
vermez. Tenant dışı ya da bağlı olunmayan daire 404 üretir.

Resident navigasyonu yalnız Dairem, Hesap hareketleri ve Çıkış seçeneklerini
gösterir. Allocation satırları arayüzde gösterilmez; kullanılmamış ödeme ayrı
sunulur ve borçtan otomatik düşülmez. Gider, duyuru, banka, belge ve online
ödeme ekranları henüz uygulanmamıştır.

## 9. Yetki matrisi

| Kaynak / işlem | Platform SA | Org admin | Building manager | Resident |
|---|---:|---:|---:|---:|
| Organization oluşturma/durum | Evet | Hayır | Hayır | Hayır |
| Domain yönetimi | Evet | Talep/görüntüleme opsiyonel | Hayır | Hayır |
| Branding | Denetim | Kendi org | Hayır | Hayır |
| Bina oluşturma | Denetim | Kendi org | Hayır | Hayır |
| Manager atama | Denetim | Kendi org | Hayır | Hayır |
| Daire/sakin yönetimi | Destek politikasıyla | Kendi org | Atandığı bina | Hayır |
| Finansal hareket yazma | Destek politikasıyla | Kendi org | Atandığı bina | Hayır |
| Banka/gider/duyuru yazma | Destek politikasıyla | Kendi org | Atandığı bina | Hayır |
| Dört resident görünümü | Varsayılan hayır | Kendi org | Atandığı bina | Bağlı bina/daire |
| Audit görüntüleme | Platform kapsamı | Sınırlı/karar bekliyor | Hayır | Hayır |

Platform super admin'in müşteri verisine destek amaçlı erişimi otomatik kabul edilmemelidir. Ayrı impersonation/break-glass politikası, gerekçe, süre ve audit gerektirir.

## 10. IDOR koruması

Yanlış:

```text
expense = find_by_id(expense_id)
```

Gerekli sorgu anlamı:

```text
expense = find_visible_expense(
  organization_id=tenant.id,
  building_ids=principal.allowed_building_ids,
  expense_id=expense_id
)
```

Aynı ilke update, delete/archive, belge indirme ve nested route'lar için geçerlidir. Route'taki `building_id` ile kaydın gerçek `building_id` değeri eşleştirilir.

## 11. Dosya indirme yetkisi

Belge public static URL ile sunulmaz. İndirme route'u:

1. Tenant'ı hosttan çözer.
2. Document'i tenant kapsamında getirir.
3. İlişkili expense/building görünürlüğünü kontrol eder.
4. Status `active` olmalı; harici tarama etkinse scan durumu `clean`, etkin değilse onaylı `not_required` politikası olmalıdır.
5. Audit/purpose gereksinimini uygular.
6. MVP'de yetkili Flask endpoint'i üzerinden stream eder.

Resident yalnız aktif apartment membership ile eriştiği binadaki `residents` görünürlüklü gider belgesini indirebilir. Pasif/sona ermiş membership geçmiş belgeye otomatik erişim vermez. İndirme yetkili Flask endpoint'inden yapılır; dosya organization ve ilişkili entity kapsamı doğrulanır. Branding asset'leri ayrı, kontrollü public-cache politikasına sahip olabilir.

## 12. Kesinleşen sınırlar ve kalan kararlar

- Organization admin'in tüm bina operasyonlarını yapabilmesi önerilir fakat ürün kararı gerekir.
- Platform super admin ve destek personelinin tenant verisine normal/sınırsız erişimi kapalıdır. Gerekirse süreli, gerekçeli, açıkça yetkilendirilmiş ve audit kayıtlı break-glass oturumu kullanılır.
- Resident birden çok daireye bağlıysa açık daire seçici kullanılır.
- Resident yalnız aktif membership dönemini görür; bitmiş üyelik erişim vermez.
- Platform super admin için production girişinde MFA zorunludur; organization admin için desteklenir ve politika ile zorunlu yapılabilir.
- Route isimleri uygulama tasarımında küçük değişiklik gösterebilir; güvenlik semantiği değişmez.
- API-first JSON endpoint'leri MVP kapsamı değildir.

## 13. Riskler

- UI'da gizlenen butonlar yetkilendirme değildir.
- Nested URL'de parent-child eşleşmesi doğrulanmazsa IDOR oluşur.
- Merkezi platform hostunda tenant route'larının açılması güvenlik ve marka karışıklığı yaratır.
- Platform destek erişiminin sınırsız bırakılması iç tehdit riskini yükseltir.

## 14. Uygulanan yönetim route'ları

Platform hostname üzerinde `platform_admin_required` ile:

- `/platform/organizations` liste, arama ve sayfalama
- `/platform/organizations/new` ve `/<organization_id>/edit`
- `/<organization_id>/branding`
- `/<organization_id>/domains` ile domain ekleme, primary, activate ve suspend
- `/<organization_id>/admins` ile mevcut/yeni kullanıcıyı admin atama

Tenant hostname üzerinde `organization_admin_required` ile:

- `/organization/buildings` ve bina oluşturma/düzenleme
- Bina altında daire listeleme/oluşturma ve scoped daire düzenleme
- `/organization/users` ve kullanıcı/organization membership oluşturma
- Organization, building ve apartment membership POST işlemleri
- Membership fiziksel silme yerine POST ile pasifleştirme
- `GET /organization/dues` ile aktif bina ve dönem bazlı aidat özeti
- `POST /organization/dues/batches` ile aktif dairelere toplu aidat oluşturma
- `GET /organization/dues/apartments/<apartment_id>` ile scoped daire finans detayı
- `POST /organization/dues/apartments/<apartment_id>/payments` ile ödeme ve
  isteğe bağlı en eski borçtan başlayan otomatik mahsup

Tenant dışı detay ve mutation hedefleri 404 verir. Aynı tenant içinde rol
yetersizliği 403 verir. State değiştiren endpoint'ler GET kabul etmez ve CSRF
korumasındadır.

Aidat ekranındaki tahsilat yalnız seçili dönem borçlarına bağlı geçerli ödeme
dağıtımlarından hesaplanır. Önceki dönem borcu varsa otomatik mahsup önce o
borca gider ve ödeme tutarının tamamı seçili dönem tahsilatı gibi gösterilmez.
Arayüz teknik finans model adlarını göstermez. Resident gider ve banka
modülleri henüz uygulanmamıştır.
