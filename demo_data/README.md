# Yapıbina demo veri paketi

Bu dizindeki veriler tamamen kurgusaldır. İsimler temsili olarak üretilmiş,
telefonlar `DEMO-` öneki taşımakta ve tüm e-postalar `example.com` alan adını
kullanmaktadır.

Yapıbina, Apsiyon'un yerine geçen bir operasyon veya muhasebe sistemi değildir.
Bu paket Apsiyon adapter'ından bağımsız Yapıbina standart ara veri formatını
örnekler. Dosyalar henüz uygulama veritabanına import edilmemektedir ve gerçek
Apsiyon adapter'ı ya da tarayıcı otomasyonu mevcut değildir.

Üretim ve doğrulama:

```bash
python scripts/generate_demo_data.py
python scripts/validate_demo_data.py
python scripts/validate_demo_data.py --path demo_data
```

Paket 1 Şubat–31 Temmuz 2026 arasında beş kurgusal site, 50 bağımsız bölüm,
50 resident, aidat/ödeme senaryoları, giderler ve duyurular içerir.
