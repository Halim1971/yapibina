# Yardımcı betikler

Demo veri paketi proje kökünden şu komutlarla yönetilir:

```bash
python scripts/generate_demo_data.py
python scripts/validate_demo_data.py
python scripts/validate_demo_data.py --path demo_data
```

Generator yalnız hedef dizini güvenli kontrollerden sonra yeniden oluşturur.
Validator schema, referans, kontrollü senaryo, manifest hash ve ikinci üretimin
byte düzeyinde aynı olması kontrollerini yapar. Bu araçlar importer değildir ve
uygulama veritabanına yazmaz.
