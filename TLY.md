# TLY Risk Monitor — Proje Dokümantasyonu

> Tera Portföy Birinci Serbest Fon (TLY) için risk analizi, stres testi ve para akışı izleme aracı.
> Her değişiklik sonrası bu dosyayı da güncelle.

---

## Çalıştırma

```bash
# Web arayüzü (ana kullanım)
streamlit run app.py

# Terminal raporu
python main.py

# Android (Kivy)
python main_android.py
```

---

## Dosya Yapısı ve Sorumluluklar

| Dosya | Görev | Kim Kullanıyor |
|---|---|---|
| `app.py` | Streamlit web arayüzü (tüm analizleri gösterir) | Kullanıcı |
| `main.py` | Terminal tabanlı CLI giriş noktası | CI/script |
| `main_android.py` | Kivy mobil arayüz (Pydroid3 / APK) | Mobil |
| `config.py` | Portföy tanımları, eşikler, API anahtarı | Tüm modüller |
| `data_fetcher.py` | yfinance ile hisse verisi çekme | app.py, main.py |
| `risk_analyzer.py` | 4 kural risk motoru (likidite, rotasyon, sistemik, sığ piyasa) | app.py, main.py |
| `simulator.py` | T+2 valör panik simülasyonu | app.py, main.py |
| `tefas_fetcher.py` | TEFAS'tan TLY fon sağlığı (NAV, AUM, yatırımcı) | app.py, main.py |
| `stress_test.py` | Stres testi: Fonoloji holdings + TEFAS birleşik analizi | app.py, main.py |
| `money_flow.py` | **YENİ** — Gelişmiş para akışı analizi (tüm geçmiş) | app.py |
| `reporter.py` | Terminal rapor formatı (colorama + tabulate) | main.py |
| `TLY.md` | **Bu dosya** — proje dokümantasyonu | Claude |

---

## `config.py` — Portföy Tanımı

Son güncelleme: **8 Haziran 2026**

```python
PORTFOLIO = {
    "DSTKF.IS": {"name": "Destek Faktoring",  "weight": 17.71, "category": "anchor"},
    "OZATD.IS": {"name": "Ozata Denizcilik",  "weight": 17.16, "category": "anchor"},
    "TERA.IS":  {"name": "Tera Yatirim",      "weight": 11.50, "category": "group"},
    "PEKGY.IS": {"name": "Peker GYO",          "weight": 9.89,  "category": "other"},
    "TRHOL.IS": {"name": "Tera Finansal",      "weight": 6.59,  "category": "group"},
    "TEHOL.IS": {"name": "Tera Teknoloji",     "weight": 5.50,  "category": "group"},
}

EQUITY_RATIO = 71.54      # Fonun hisse oranı (%)
DEFAULT_CAPITAL = 500_000  # Varsayılan anapara (TL)
PANIC_RATE = 10.0          # Günlük panik senaryosu (%)

# Eşikler
WEIGHT_THRESHOLD = 10.0
PRICE_DROP_THRESHOLD = -5.0
VOLUME_LOCKDOWN_THRESHOLD = 0.50   # %50 altı → likidite kilitlenmesi
VOLUME_THIN_MARKET_THRESHOLD = 0.20 # %20 altı → sığ piyasa
CORRELATION_THRESHOLD = 0.80       # korelasyon eşiği
GROUP_TICKERS = ["TERA.IS", "TRHOL.IS", "TEHOL.IS"]

FONOLOJI_API_KEY = ""  # Fonoloji API anahtarı
```

**Güncelleme talimatı:** Her KAP raporu sonrası `weight`, `prev_weight` ve `EQUITY_RATIO` değerlerini güncelleyin. `prev_weight` bir önceki ayın ağırlığıdır — rotasyon tespiti için kullanılır.

---

## Risk Kuralları (risk_analyzer.py)

### KURAL 1 — Likidite Kilitlenmesi
- Ağırlık > %10 **VE** fiyat < -%5 **VE** hacim < ortalamanın %50'si
- Üçü aynı anda → `is_critical = True` (🔴)

### KURAL 2 — Başarılı Çıkış (False Positive Filtresi)
- Fiyat düşüyor **VE** hacim yüksek **VE** ağırlık azalmış
- → Rotasyon olarak işaretlenir, **alarm verilmez** (🔵)

### KURAL 3 — Sistemik Çöküş Radarı
- TERA grubu (TERA, TRHOL, TEHOL) arası 30 günlük korelasyon
- Korelasyon > 0.80 **VE** üçü de aynı gün negatif → sistemik risk

### KURAL 4 — Sığ Piyasa Uyarısı
- Ağırlık > %10 **VE** hacim < ortalamanın %20'si
- Fiyat yönünden bağımsız, erken uyarı (🟡)

---

## Stres Testi (stress_test.py)

TEFAS + Fonoloji verilerini birleştirir:

| Metrik | Kaynak |
|---|---|
| NAV, AUM, yatırımcı sayısı | TEFAS (pytefas) |
| Ters repo oranı, nakit tamponu | Fonoloji API |

**5 stres kuralı:**
1. Nakit tamponu <%10 → KRİTİK
2. Yatırımcı 7 günde >%3 düşüş → KRİTİK
3. AUM 7 günde >%5 düşüş → KRİTİK
4. NAV 5 gün art arda düşüş → UYARI
5. 2+ kural aynı anda → SİSTEMİK STRES

---

## Para Akışı Analizi (money_flow.py) — YENİ

### Veri kaynağı
- `pytefas` ile 2021-06-15'ten bugüne tüm TLY verisi
- `@st.cache_data(ttl=3600)` ile 1 saat cache

### Hesaplamalar

**Günlük net akış:**
```
net_akis = (bugun_AUM - dun_AUM) - (dun_AUM × nav_degisim_yuzdesi / 100)
```
Bu formül AUM değişiminden NAV kaynaklı değişimi çıkararak gerçek para giriş/çıkışını bulur.

**Aylık agregasyon:** Toplam net akış, ortalama günlük akış, işlem günü sayısı, AUM değişimi (%), yatırımcı değişimi, 12 aylık hareketli ortalama.

**Haftalık ivme:** `ivme = bu_hafta_ortalama - gecen_hafta_ortalama`

**Uzun vade istatistikler:** Tüm dönem ortalaması, standart sapma, en yüksek/büyük giriş/çıkış ayı (tarih ile), her ayın tarihsel ortalaması (mevsimsel desen).

### 4 Uyarı Kuralı

| Kural | Tetikleyici | Mesaj |
|---|---|---|
| Mevsimsel karşılaştırma | Geçen yıl aynı ay da çıkış → bu yıl da çıkış | 📅 Mevsimsel çıkış olabilir |
| Mevsimsel anomali | Geçen yıl giriş → bu yıl çıkış | ⚠️ Mevsimsel anomali |
| İvme kaybı | 3 hafta üst üste ivme düşüyor | ⚠️ ERKEN UYARI |
| Tarihsel dışlık | Aylık çıkış > 2 std sapma | 🚨 TARİHSEL DIŞLIK |

### app.py'deki UI bileşenleri
- **Sidebar:** Dönem seçici (Son 60 gün / 6 Ay / 1 Yıl / 3 Yıl / Tümü / Özel tarih) + Mevsimsel Mod toggle
- **Özet Dashboard:** 4 büyük metrik (Bu Ay Akış, İvme Durumu, Uzun Vade Ort, Mevsimsel Uyum)
- **Akıllı Yorum:** Kural tabanlı otomatik tek paragraf değerlendirme
- **Mevcut Ay Vurgusu:** Bu ayın tarihsel profile uyumu (expandable)
- **Export:** "Raporu İndir (Excel)" butonu — 3 sheet'li Excel (Aylık Akış, Mevsimsel Takvim, Haftalık İvme)
- **Mevsimsel Takvim Tablosu:** 12 aylık (Tarihsel Ort, Pozitif Yıl, Değerlendirme, En İyi/Kötü Yıl) — mevcut ay mavi vurgulu
- **Karşılaştırma kartı:** 4 metrik (dönem ort., uzun vade ort., fark %, z-score) + değerlendirme
- **Grafik 1:** Aylık bar chart (yeşil/kırmızı barlar + turuncu 12A HA çizgisi + mor mevsimsel referans çizgileri)
- **Grafik 2:** AUM ve Net Akış çift eksenli karşılaştırma
- **Grafik 3:** Haftalık ivme nokta grafiği (sıfır çizgisi referans)
- **Tablo:** Aylık akış listesi (Ay, Net Akış, AUM %, Yatırımcı Değişimi, Değerlendirme)

### Kullanılan fonksiyonlar
- `fetch_full_history()` — Tüm geçmiş TEFAS verisi (2021-06-15 → bugün)
- `calc_daily_net_flow(df)` — Günlük net akış hesaplama
- `aggregate_monthly(daily_df)` — Aylık agregasyon
- `calc_weekly_momentum(daily_df)` — Haftalık ivme
- `calc_long_term_stats(monthly_df)` — Uzun vade istatistikler
- `calc_seasonal_calendar(monthly_all)` — 12 aylık mevsimsel takvim (ort, pozitif yıl, en iyi/kötü yıl)
- `current_month_highlight(calendar, monthly)` — Mevcut ayın tarihsel profile uyumu
- `generate_warnings(...)` — 4 uyarı kuralı
- `generate_commentary(...)` — Kural tabanlı akıllı yorum
- `calc_comparison(...)` — Dönem karşılaştırması (%, z-score, değerlendirme)
- `export_to_excel(...)` — 3 sheet'li Excel çıktısı (BytesIO)
- `analyze_money_flow(df, period_start, period_end)` — Ana orkestratör

---

## app.py — Streamlit Web Arayüzü (Bölüm Sırası)

1. **Başlık** — TLY Risk Analiz Raporu, bugünün tarihi
2. **Portföy Özeti** — 5 metrik kartı (toplam hisse, veri gelen, kritik hisseler, sistemik risk, hisse değeri)
3. **Risk Skoru Tablosu** — Hisse bazlı renkli tablo (🔴🔵🟡🟢)
4. **Sistemik Risk** — Korelasyon göstergesi + progress bar
5. **T+2 Valör Simülasyonu** — 3 günlük panik senaryosu
6. **Uyarılar & Loglar** — Kritik, rotasyon, sığ piyasa
7. **Fon Sağlığı (TEFAS)** — NAV, AUM, yatırımcı metrikleri (30 günlük)
8. **Stres Testi** — 5 metrik + nakit tamponu + stres seviyesi
9. **Para Akışı Analizi** — Dashboard (4 metrik), akıllı yorum, mevcut ay vurgusu, export butonu, mevsimsel takvim tablosu, karşılaştırma kartı, 3 grafik (mevsimsel ref çizgili), uyarılar, aylık akış tablosu
10. **Alt bilgi**

---

## Bağımlılıklar

```
streamlit>=1.50
yfinance>=0.2.0
pandas>=2.0
numpy>=1.24
colorama>=0.4
tabulate>=0.9
pytefas>=0.4.0
plotly>=6.0
openpyxl>=3.0
kivy>=2.3          # sadece Android için
```

---

## Hata Yönetimi Stratejisi

Tüm harici veri çekme fonksiyonları hata durumunda **None döner**, programı çökertmez:
- `yfinance` başarısız → `data["error"] = True`, tablo "VERİ YOK" gösterir
- `pytefas` başarısız → `None`, UI "çekilemiyor" gösterir
- `Fonoloji API` başarısız → `None`, stres testi onsuz çalışır

---

## Değişiklik Geçmişi

| Tarih | Commit | Açıklama |
|---|---|---|
| 2026-06-18 | — | Mevsimsel takvim, akıllı yorum, 4-metrik dashboard, mevsimsel mod, Excel export eklendi |
| 2026-06-18 | — | money_flow.py eklendi, app.py'ye para akışı analizi UI'ı entegre edildi |
| 2026-06-18 öncesi | cdee046 | Stress test modülü eklendi |
| 2026-06-18 öncesi | 00f5742 | pytefas eklendi |
| 2026-06-18 öncesi | aa1fa75 | TEFAS kapalıyken hata düzeltmesi |
| 2026-06-18 öncesi | 5a7e2f1 | Streamlit app eklendi |
