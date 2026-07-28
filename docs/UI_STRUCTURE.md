# Yapıbina Arayüz Yapısı

## 1. Tasarım ilkeleri

- Mobil öncelikli, hızlı ve sade
- Güven veren, gösterişsiz görsel dil
- Büyük ve okunabilir finansal değerler
- Bol beyaz alan ve belirgin bilgi hiyerarşisi
- Karmaşık menü, jargon ve gereksiz dashboard öğesi yok
- Klavye erişimi, görünür focus, yeterli kontrast ve anlamlı hata mesajları
- Resident ile yönetim arayüzleri açıkça ayrılır

## 2. Giriş ekranı

Gelen domainin organization markası çözülür. Ekran:

- Logo veya varsayılan Yapıbina logosu
- Panel başlığı
- İsteğe bağlı kısa giriş mesajı
- E-posta ve parola
- Parolayı unuttum
- Destek iletişimi

Organization bulunamazsa müşteri markası gösterilmez. Hatalı giriş yanıtı hesap varlığını veya başka organization üyeliğini ifşa etmez.

## 3. Platform super admin ekranları

- Organization listesi ve durum filtreleri
- Organization detay ve kullanım özeti
- Geçici/özel domain yaşam döngüsü
- Paket/kullanım durumu (ürün modeli netleşince)
- Platform sağlık ve hata görünümü
- Audit arama

Bu ekranlar merkezi platform hostunda, müşteri panelinden ayrı görsel bağlamda bulunur.

## 4. Organization admin ekranları

- Organization dashboard
- Firma ve iletişim bilgileri
- Marka/tema önizleme
- Kullanıcı ve davet yönetimi
- Bina listesi ve bina oluşturma
- Building manager atama
- Organization kapsamındaki operasyonlara geçiş

Dashboard yalnız eylem gerektiren özetleri göstermelidir: aktif bina sayısı, bekleyen davet, domain durumu ve kritik operasyon uyarıları.

## 5. Building manager ekranları

- Yetkili bina seçici
- Bina dashboard'u
- Daire ve sakin listeleri
- Borç/ödeme/ters kayıt işlemleri
- Banka hareketi ve import
- Gider, kategori, belge ve eşleştirme
- Duyuru hazırlama/yayınlama

Bina seçimi kalıcı görünür olmalı; aktif bina adı tüm kritik formlarda tekrar gösterilmelidir. Finansal onay ekranında daire, tutar, yön ve tarih açıkça özetlenir.

## 6. Resident ekranları

Resident'ın ana navigasyonu yalnız:

1. Ekstrem
2. Banka
3. Giderler
4. Duyurular

Birden fazla daire varsa üst alanda açık bir daire seçici bulunur. Seçim yalnız kullanıcının yetkili dairelerinden yapılabilir.

### Ekstrem

- Üstte büyük güncel bakiye
- Borç/alacak durumunu yalnız renkle değil metin ve işaretle anlatma
- Dönem filtresi
- Tarih, açıklama, borç, ödeme ve kalan bakiye
- Ödenmiş/ödenmemiş durum rozetleri yalnız gerçek allocation modeli varsa
- Mobilde satır yerine taranabilir hareket kartları veya yatay taşmayan liste

### Banka

- Tarihe göre ters kronolojik liste
- Giriş/çıkış etiketi
- Tutar, tarih, açıklama ve referans
- Filtreler sade ve açılır panelde
- Hesap numarası gibi hassas bilgiler ürün kararı olmadan gösterilmez

### Giderler

- Tarih, kategori, açıklama, firma/kişi ve tutar
- Belge varsa belirgin fakat ikincil “Belgeyi görüntüle”
- Banka hareketiyle eşleşme bilgisi
- Mobilde kart, masaüstünde liste/tablo seçeneği

### Duyurular

- Okunmadı işareti, başlık, yayın tarihi, kısa özet
- Detayda tam içerik ve geçerlilik bilgisi
- Okundu durumu detay açıldığında idempotent biçimde işlenir

## 7. Navigasyon

### Mobil

Resident için sabit alt navigasyon dört eşit öğeden oluşur. Etiketler ikonla birlikte gösterilir; yalnız ikona güvenilmez. Güvenli alan payları ve 44x44 px asgari dokunma hedefi gözetilir.

Yönetim mobil görünümünde dört resident menüsü taklit edilmez; ana görevler dashboard ve sade açılır menüyle sunulur. Çok sayıda operasyon alt navigasyona sıkıştırılmaz.

### Masaüstü

Resident'ta üst veya dar yan navigasyon dört öğeyi gösterir. Yönetim arayüzünde rol ve aktif bina bağlamını gösteren sol navigasyon kullanılabilir. Organization değiştirme yalnız üyelik varsa ve host/domain güvenlik modeliyle uyumlu yönlendirme üzerinden yapılır.

## 8. Dashboard kartları

Kartlar karar vermeye yardım etmelidir. Öneriler:

- Yönetim: toplam açık bakiye, son banka hareketleri, belgesiz giderler, aktif duyuru
- Resident: yalnız güncel bakiye, son hareket ve okunmamış duyuru sayısı

Dekoratif grafikler MVP'ye eklenmez. Sayılar açıklama, dönem ve para birimiyle birlikte gösterilir.

## 9. Formlar

- Etiket her zaman görünür; placeholder etiket yerine geçmez.
- Zorunlu alanlar belirtilir.
- Türkiye para girişi kullanıcı dostu olsa da sunucuda kesin Decimal'e normalize edilir.
- Hata ilgili alanın yanında ve sayfa özetinde gösterilir.
- Kritik finansal işlemde son onay özeti bulunur.
- Çift gönderim önlenir; buton durumu tek başına güvenlik değildir.
- Dosya alanında tür/boyut sınırları yüklemeden önce açıklanır.

## 10. Tablolar ve listeler

- Masaüstünde sabit ve anlamlı sütunlar
- Mobilde öncelikli alanları koruyan kart/list görünümü
- Sıralama ve filtre durumu görünür
- Sayfalama sunucu taraflı
- İşlem menüsü satır bağlamını açıkça belirtir
- Finansal tutarlar sağa hizalı, tabular numeral destekli
- Durum yalnız renkle anlatılmaz

## 11. Boş durumlar

Her boş durum:

- Neyin bulunmadığını söyler
- Bunun normal olup olmadığını açıklar
- Yetkili role tek bir sonraki eylem sunar

Resident'a yapamayacağı “ekle” çağrısı gösterilmez. Filtre sonucu boşluğu ile sistemde hiç kayıt olmaması ayrılır.

## 12. Başarı ve hata mesajları

- Başarı mesajı yapılan işlemi somut söyler.
- Finansal kayıt sonrası tutar, daire ve referans gösterilir.
- Validation hatası kullanıcı verisini mümkün olduğunca korur.
- Yetki hatası hassas kaynak varlığını doğrulamaz.
- Sistem hatasında request ID gösterilir; teknik stack trace gösterilmez.
- Toast yalnız geçici bilgi içindir; kritik hata kalıcı sayfa içi mesajdır.

## 13. Tema ve renkler

Varsayılan Yapıbina değerleri:

```text
Ana:       #0f3f3f
İkincil:   #d4d9d5
Yüzey:     #f4f4f4
Beyaz:     #ffffff
```

Uygulama aşamasında bunlar CSS custom properties olarak merkezi tanımlanmalıdır:

```text
--color-primary
--color-secondary
--color-surface
--color-white
```

Organization değerleri doğrulandıktan sonra request kapsamındaki tema çıktısında override edilir. Eksik değerler tek tek varsayılana döner. Müşteri rengi metin/arka plan kontrastını bozuyorsa erişilebilir güvenli varyant veya reddetme politikası uygulanır. Her müşteriye ayrı HTML/CSS üretilmez.

## 14. Yerelleştirme

- Dil: başlangıçta Türkçe
- Para: `1.234,56 ₺` benzeri Türkiye biçimi
- Tarih: `28.07.2026`
- Saat: arayüzde Europe/Istanbul
- Veritabanı: UTC

Formatlama view/template helper'larında merkezi yapılır; kayıtlı sayısal değer metin formatından ayrıdır.

## 15. Varsayımlar, belirsizlikler ve riskler

Varsayımlar:

- Resident içerikleri düz metin veya çok sınırlı güvenli biçimlendirmedir.
- Yönetim ve resident aynı responsive web uygulamasındadır, fakat ayrı layout kullanır.

Belirsizlikler:

- Organization admin dashboard metriklerinin kesin tanımı
- “Ödenmiş” işaretinin allocation olmadan nasıl hesaplanacağı
- Çok daireli resident için varsayılan daire seçimi
- Marka renklerinde minimum kontrast politikasının ürün davranışı

Riskler:

- Çok fazla yönetim işlevini tek ekrana toplamak sadeliği bozar.
- Rengin finansal anlam için tek sinyal olması erişilebilirliği bozar.
- White-label taleplerinin layout özelleştirmesine genişlemesi bakım yükü yaratır.

