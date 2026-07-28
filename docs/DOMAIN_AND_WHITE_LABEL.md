# Domain ve White-label Mimarisi

## 1. Amaç

Her organization, aynı Yapıbina uygulamasını kendi markasıyla ve tercihen kendi alan adındaki bir alt alan adıyla kullanır. Domain, yalnız marka adresi değil, aktif tenant'ın güvenlik açısından belirlenmesinde kullanılan doğrulanmış girdidir.

Desteklenen modeller:

- Geçici Yapıbina alt alan adı: `lina.yapibina.com`
- Müşteri özel alt alan adı: `panel.linabinayonetimi.com`

Path tabanlı tenant (`musterialanadi.com/panel`) MVP kapsamı dışındadır.

## 2. Domain veri ve durum modeli

Her organization birden fazla domain kaydına sahip olabilir. Hostname global benzersizdir.

MVP domain state machine:

```text
pending
  -> awaiting_dns
  -> dns_verified
  -> ssl_pending
  -> active

Her ara durum -> failed (neden ve tekrar deneme kaydıyla)
active/failed -> suspended (yetkili operasyonla)
suspended -> awaiting_dns veya ssl_pending (sorunun türüne göre kontrollü yeniden başlatma)
```

Veritabanındaki `status`, `ssl_status`, `is_active` ve `is_primary` alanları bu yaşam döngüsünü temsil eder. Geçişler yalnız izin verilen service operasyonlarıyla ve audit kaydıyla yapılır. Aktivasyon koşulu: organization aktif, DNS doğrulanmış, SSL hazır, Nginx configuration testi başarılı ve reload tamamlanmış.

## 3. Yapıbina alt alan adı

Organization oluşturulduğunda benzersiz ve normalize edilmiş bir slug ayrılır. Ayrılan kelimeler, yanıltıcı adlar ve mevcut özel domainlerle çakışmalar reddedilir.

DNS yaklaşımı:

- `*.yapibina.com` için wildcard DNS uygulama sunucusuna yönlenebilir.
- Wildcard TLS sertifikası veya kontrollü host başına sertifika kullanılabilir.
- Wildcard DNS her hostname'i teknik olarak sunucuya getirse bile uygulama yalnız veritabanında aktif kayıtlı hostname'i kabul eder.

Geçici domain, özel domain hazır olana kadar çalışır. Özel domain primary olduğunda geçici domain yedek erişim olarak aktif tutulabilir; bunun ürün ve güvenlik etkisi açık politika olmalıdır.

## 4. Müşteri özel alt alan adı

Tercih edilen müşteri kaydı:

```text
panel.musterialanadi.com CNAME tenant-entry.yapibina.com
```

Alternatif A/AAAA kullanımı IP değişikliklerinde operasyon yükü yaratır; zorunlu değilse CNAME önerilir. Apex domain kapsam dışıdır ve CNAME kısıtları nedeniyle ayrıca ele alınır.

Süreç:

1. Platform yöneticisi veya yetkili onboarding süreci domain talebi açar.
2. Host normalize edilir ve sahiplik/çakışma kontrolleri yapılır.
3. Kriptografik token üretilir; veritabanında hash'i saklanır.
4. Müşteriye `_yapibina-verify.panel...` gibi TXT kaydı talimatı verilir.
5. Sistem authoritative DNS üzerinden TXT ve yönlendirme kayıtlarını kontrol eder.
6. Başarılı doğrulamanın zamanı ve yöntemi kaydedilir.
7. Yetkili operatör Nginx yapılandırmasını kontrollü hazırlar.
8. Let's Encrypt/Certbot ile sertifika alınır.
9. Nginx configuration testi zorunlu olarak çalıştırılır; başarısızsa aday config etkinleştirilmez ve reload yapılmaz.
10. Başarılı testten sonra Nginx kontrollü reload edilir.
11. HTTPS health kontrolünden sonra domain aktive edilir.
12. İstenirse primary yapılır.

DNS doğrulama sonucu cache/TTL nedeniyle gecikebilir. Kontrol işlemi rate-limitli, tekrar denenebilir ve idempotent olmalıdır.

## 5. Domain doğrulama

Yalnız CNAME'in uygulama sunucusuna işaret etmesi sahiplik kanıtı olarak yeterli kabul edilmemelidir. TXT token önerilir. Token:

- Yeterli entropiye sahip olmalı
- Domain ve organization'a bağlanmalı
- Süreli ve döndürülebilir olmalı
- Loglarda ve audit `new_values` içinde ham biçimde bulunmamalı
- Başarılı doğrulamadan sonra yeniden kullanılamamalı

DNS rebinding ve dangling DNS riskleri için aktivasyon öncesi ve periyodik kontroller düşünülebilir. Doğrulama kaybı otomatik ve ani kesinti yaratmadan uyarı/inceleme sürecine girmelidir.

## 6. SSL ve MVP işletim modeli

Let's Encrypt/Certbot kullanılır. İlk MVP'de sertifika alma ve Nginx provisioning kontrollü manuel operasyondur; tam otomatik ACME zorunlu değildir.

Certbot challenge yöntemi production runbook hazırlanırken sunucu/DNS koşuluna göre belirlenir. Sertifika hazır olmadan domain aktif edilmez. Yenileme kontrolü, expiry alarmı ve başarısız yenileme runbook'u gerekir. State modeli ileride otomatik provisioner'ın aynı geçişleri idempotent biçimde yürütmesine uygundur.

Sertifika dosya izinleri en az yetkiyle sınırlandırılır. TLS modern protokollerle yapılandırılır; HSTS ilk yayında dikkatle ve domain kontrolü kesinleştikten sonra etkinleştirilir.

## 7. Nginx yaklaşımı

Nginx:

- HTTP'yi HTTPS'ye yönlendirir.
- Orijinal `Host` bilgisini Flask'a iletir.
- Yalnız beklenen proxy header'larını set eder.
- İstek ve yükleme boyutu sınırını uygular.
- Statik uygulama varlıklarını sunar.
- Private müşteri belgelerini doğrudan servis etmez.
- Tüm doğrulanmış özel domainleri aynı Gunicorn upstream'ine yönlendirebilir.

MVP'de yetkili operatör kontrollü Nginx config şablonu kullanır. Kullanıcı girdisi config'e doğrudan eklenmez; hostname sıkı doğrulanır. Değişiklik ayrı bir aday dosyada hazırlanır, configuration testinden geçmeden etkin konuma alınmaz ve reload yapılmaz. Son bilinen iyi yapılandırma korunur; tek domain hatası mevcut müşterilerin server block'larını bozmamalıdır. Nginx değişikliği uygulama transaction'ından ayrı dış operasyon olduğundan durum makinesi ve telafi işlemi gerekir. Gelecekte aynı kuralları kullanan otomatik provisioner eklenebilir.

## 8. Host bazlı tenant çözümleme

Uygulama:

1. Güvenilir request host kaynağını alır.
2. Portu kaldırır, lower-case/IDNA normalize eder.
3. CRLF, slash, boşluk, wildcard ve geçersiz label içeren hostu reddeder.
4. Aktif + doğrulanmış + SSL-ready domain kaydını exact match arar.
5. Bağlı aktif organization ile tenant context kurar.

Hostname cache'lenebilir; cache anahtarı normalize host, değeri organization ID ve domain sürümüdür. Aktivasyon/pasifleştirme değişikliklerinde cache invalidation zorunludur. Cache miss asla “varsayılan tenant”a düşmez.

## 9. Birden fazla domain ve primary domain

- Organization'ın yalnız bir aktif primary domaini olur.
- Secondary aktif domainler aynı tenant'a çözülür.
- Canonical yönlendirme istenirse yalnız veritabanındaki doğrulanmış primary HTTPS URL'sine yapılır.
- POST istekleri domainler arasında otomatik yönlendirilmez; oturum ve CSRF etkileri nedeniyle güvenli hata/yeniden giriş tercih edilir.
- Cookie'ler host-only tutulur; `.yapibina.com` çapında paylaşılmaz.
- Domain değişiminde eski domain belirli geçiş süresince secondary kalabilir.

Geçici Yapıbina domaininin özel domain sonrasında açık kalması müşteri tercihine ve destek politikasına bağlanmalıdır.

## 10. Domain değişikliği

1. Yeni domain ayrı kayıt olarak eklenir.
2. DNS ve SSL tamamen hazırlanır.
3. Yeni domain aktif secondary olarak test edilir.
4. Kontrollü biçimde primary yapılır.
5. Oturumların host-only olması nedeniyle kullanıcı yeniden giriş yapabilir.
6. Eski domain geçiş süresi sonunda pasifleştirilir.
7. Tüm aşamalar audit'e yazılır.

Eski hostname hemen başka organization'a tahsis edilmemeli; karantina süresi uygulanmalıdır.

## 11. Pasifleştirme

Domain; müşteri talebi, organization suspend durumu, güvenlik olayı veya doğrulama kaybıyla pasifleştirilebilir. Pasifleştirme:

- Tenant çözümleme cache'ini temizler.
- Uygulama erişimini keser.
- Sertifikayı hemen silmek yerine retention/runbook uygular.
- Primary ise önce başka doğrulanmış domain seçilmesini gerektirir.
- Audit ve operasyon alarmı üretir.

## 12. Bilinmeyen host davranışı

Önerilen varsayılan: markasız `421 Misdirected Request` veya `404`, `Cache-Control: no-store`. Host değeri HTML'e kaçışsız yansıtılmaz. Merkezi sayfaya yönlendirme ürün kararı olursa yalnız sabit Yapıbina HTTPS adresine `302/307` yapılır.

Nginx default server da beklenmeyen hostları mümkün olduğunca reddeder; uygulama kontrolü ikinci savunma katmanıdır.

## 13. White-label marka çözümleme

Tenant çözüldükten sonra BrandingService:

- Organization branding kaydını alır.
- Yalnız doğrulanmış renk ve URL değerlerini kabul eder.
- Eksik alanları Yapıbina varsayılanlarıyla tamamlar.
- Logo/favicon document'lerinin aynı organization'a ait ve güvenli olduğunu doğrular.
- Tek bir ortak template/theme sistemine sonuç verir.

Varsayılan renkler korunur:

- `#0f3f3f`
- `#d4d9d5`
- `#f4f4f4`
- `#ffffff`

White-label kapalıysa Yapıbina kimliği görünür; açıkken ürün kararına göre azaltılır. Hukuki/operasyonel zorunlu metinler tema tarafından gizlenemez.

## 14. Güvenlik riskleri

| Risk | Kontrol |
|---|---|
| Host Header spoofing | Exact allowlist, güvenilir proxy, default-host reddi |
| Subdomain takeover | Domain yaşam döngüsü, yeniden tahsis karantinası |
| Yanlış organization çözümü | Global unique hostname, aktif/doğrulanmış filtre |
| Open redirect | Sabit veya kayıtlı primary hedef |
| Cookie sızıntısı | Host-only Secure cookie |
| ACME/Certbot rate limit | Manuel runbook, kontrollü tekrar ve staging sertifika testi |
| Nginx config injection | Sıkı hostname validation ve şablonlama |
| Cache stale tenant | Sürüm/TTL ve olay bazlı invalidation |
| DNS rebinding | Yeniden doğrulama ve hedef kontrolleri |

## 15. Kesinleşen sınırlar ve kalan kararlar

Varsayımlar:

- İlk müşteri domainleri alt alan adı olacaktır.
- DNS ayarını müşteri, Nginx/SSL aktivasyonunu Yapıbina işletir.
- Platformun merkezi hostu müşteri tenant hostlarından ayrıdır.
- İlk MVP domain provisioning'i kontrollü manuel operasyondur; tam otomasyon daha sonradır.

Kodlamadan/production runbook'undan önce kalan kararlar:

- Kesin platform ve tenant-entry hostname'leri
- Certbot challenge yönteminin sunucu koşullarına göre kesin seçimi
- Bilinmeyen host için 421/404/yönlendirme
- Geçici domainin özel domain sonrası açık kalma süresi
- Eski domain karantina süresi
- Domain sahipliğinin periyodik yeniden doğrulama sıklığı
