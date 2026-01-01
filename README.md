
# Akreditasyon Demo 

Bu paket, **Flask gerektirmeden** (internet/kurulum sorunu yaşamadan) iki şeyi sağlar:

1) **Python (CLI) ile PDF rapor üretimi**
2) **Basit web ekranı** (http.server) ile öğretmen girişi + canlı hesap + PDF indir

## Gereksinimler
- Python 3.10+ (3.11 OK)
- `reportlab` ve `matplotlib` (çoğu ortamda var; yoksa kurum içi offline kurulum gerekir)
- `openpyxl` sadece Excel içe aktarma için gerekebilir (bu pakette opsiyonel)

> Not: Bu demo, Flask/Jinja2 sürüm hatalarına takılmamak için **standard library web server** kullanır.

---

## 1) CLI ile PDF üret 

Klasöre gir:
```bash
cd akreditasyon_demo_v2
```

Örnek veriyle PDF üret:
```bash
python generate_report.py --out demo_rapor.pdf
```

Kendi payload JSON’unla:
```bash
python generate_report.py --in payload.json --out rapor.pdf --dump-result sonuc.json
```

---

## 2) Web ekranı (Demo #3)

Başlat:
```bash
python web_server.py
```

Tarayıcı:
- http://127.0.0.1:5000

Sol tarafta JSON’u düzenle → **Kaydet ve Hesapla** → sağda sonuçlar.
**PDF Raporu İndir** ile raporu al.

---

## Payload şeması (özet)

- `assessments`: Not bileşenleri ve ağırlıkları
- `questions`: Soru puanları + soru→DÖÇ + Bloom + hangi bileşen
- `scores`: öğrenci bazlı ham notlar
- `doc_poc_weights`: DÖÇ→PÖÇ katkı katsayıları (0..3)
- `poc_pea_map`: PÖÇ→PEA eşlemesi

`sample_payload.py` içindeki örnek, en iyi referanstır.

---

## Hesap mantığı

- Soru başarı % = ortalama_soru_puanı / max_puan
- Bileşen başarı % = bileşendeki sorular toplamı üzerinden
- DÖÇ başarı % = DÖÇ’ye bağlı sorular toplamı üzerinden (puan bazlı)
- PÖÇ başarı % = DÖÇ başarılarının katkı katsayılarıyla ağırlıklı ortalaması
- PEA = ilgili PÖÇ’lerin ortalaması (dolaylı gösterim)

Eşikler:
- Sağlandı ≥ 70
- Kısmen ≥ 50
- Sağlanmadı < 50
(`thresholds` ile değiştirilebilir)
