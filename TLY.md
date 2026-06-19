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
| `stress_test.py` | Stres testi: 10 kuralla tam geçmiş veri analizi, konsantrasyon riski | app.py, main.py |
| `rotation_tracker.py` | **YENİ** — Fonoloji aylık holdings ile rotasyon tespiti ve havuz analizi | app.py, main.py |
| `money_flow.py` | Gelişmiş para akışı analizi (tüm geçmiş) | app.py |
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
    "PEKGY.IS": {"name": "Peker GYO",          "weight": 9.89,  "category": "fund"},   # GYF — likidite kuralları uygulanmaz
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

### KOMBİNASYON KURALI A — Çift Likidite Kilidi
- OZATD hacim < %20 **VE** DSTKF hacim < %50 → 🚨 ÇİFT LİKİDİTE KİLİDİ

### KOMBİNASYON KURALI B — Grup Sarmalı
- TERA+TRHOL+TEHOL üçü de -%3 altında **VE** korelasyon > 0.80 → 🚨 GRUP SARMALI BAŞLADI

### KOMBİNASYON KURALI C — Sessiz Çöküş
- NAV 3 gün art arda düştü **VE** yatırımcı azalıyor **VE** hisse hacimleri normal → ⚠️ SESSİZ ÇÖKÜŞ
- `analyze_portfolio()` fonksiyonu opsiyonel `fund_health` parametresi alır

---

## Stres Testi (stress_test.py)

TEFAS tam geçmiş (2021-06-15'ten) + Fonoloji verilerini birleştirir.
`analyze_stress_test(df_history=None)` — opsiyonel tam geçmiş DataFrame.

| Metrik | Kaynak |
|---|---|
| NAV, AUM, yatırımcı sayısı | TEFAS (pytefas) |
| Ters repo oranı, nakit tamponu | Fonoloji API |
| Konsantrasyon oranı (AUM/yatırımcı) | TEFAS |
| Günlük AUM std (son 180g) | TEFAS |

**10 stres kuralı (otomatik seviye: 0=Düşük, 1-2=Orta, 3+=Yüksek):**
1. Nakit tamponu <%10 → 🚨 KRİTİK
2. Yatırımcı 7g < -%3 → 🚨 KRİTİK
3. Yatırımcı 7g < -%1 → ⚠️ UYARI
4. AUM 7g < -%5 → 🚨 KRİTİK
5. AUM 7g < -%2 → ⚠️ UYARI
6. NAV 5g art arda düşüş → ⚠️ UYARI
7. Konsantrasyon 30g'de %15+ arttı → ⚠️ UYARI
8. Günlük AUM değişimi > 3× std → 👁️ BİLDİRİM
9. Yatırımcı sabit + AUM 3g hafif düşüş → ⚠️ UYARI
10. 2+ kural aynı anda → 🚨 SİSTEMİK STRES

---

## Rotasyon Analizi (rotation_tracker.py) — YENİ

Fonoloji holdings API'sinden son 6 aylık veriyi (`?report_date=YYYY-MM-DD`) çeker.

### Rotasyon Tespiti
- Hisse ağırlığı 1 ayda >10 puan değişti → 🔄 HIZLI ROTASYON
- Bir hisse azalırken diğeri benzer oranda (±%30) arttı → 🔄 ROTASYON ÇİFTİ

### Havuz Takibi
- Sabit havuz: DSTKF, OZATD, TEHOL, TRHOL, PEKGY (5 hisse)
- Son 6 ayda zirve yapanlar ve taze adaylar listelenir
- Kalan aday < 2 → ⚠️ "Rotasyon edilecek yeni hisse seçeneği azalıyor"

### app.py UI
- Rotasyon geçmişi expander'ı (son ay bilgisi)
- 3 metrik kutusu: İzlenen Havuz, Zirve Yapan, Taze Aday
- Zirveler ve taze aday listesi

---

## Para Akışı Analizi (money_flow.py)

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
2. **Terimler Sözlüğü** — Tüm terimlerin açıklandığı expandable referans tablosu (📖)
3. **Portföy Özeti** — 5 metrik kartı (tooltip'li)
4. **Risk Skoru Tablosu** — Hisse bazlı renkli tablo, başlıklarda ⓘ hover tooltip + Sütun Açıklamaları expander'ı
5. **Sistemik Risk** — Korelasyon göstergesi + progress bar (tooltip'li)
6. **T+2 Valör Simülasyonu** — 3 günlük panik senaryosu (tüm metrikler tooltip'li)
7. **Uyarılar & Loglar** — Kritik, rotasyon, sığ piyasa
8. **Fon Sağlığı (TEFAS)** — NAV, AUM, yatırımcı metrikleri (tooltip'li)
9. **Stres Testi** — 10 metrik + stres seviyesi (tümü tooltip'li)
10. **Rotasyon Analizi** — Havuz durumu (3 metrik, tooltip'li)
11. **Para Akışı Analizi** — Dashboard (4 metrik, tooltip'li), akıllı yorum, mevcut ay vurgusu, export, mevsimsel takvim, karşılaştırma kartı, 3 grafik, uyarılar, aylık akış tablosu
12. **Alt bilgi**

**Tooltip stratejisi:** Tüm `st.metric()`, `st.number_input()`, `st.slider()`, `st.radio()`, `st.toggle()` widget'larında `help=` parametresi kullanılır. HTML tablo başlıklarında `title` attribute ile hover tooltip. Her bölüm altında açıklama expander'ları.

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
| 2026-06-19 | — | risk_analyzer.py: Sayısal tip zorlaması (float/int) eklendi, tüm karşılaştırmalar TypeError'a karşı korumalı |
| 2026-06-19 | — | app.py: analyze_portfolio çağrısına try/except eklendi, hata detayı gösteriliyor |
| 2026-06-19 | — | reporter.py: print_stress_test'ten mükerrer NAV/AUM/yatırımcı satırları çıkarıldı (print_fund_health ile çakışıyordu) |
| 2026-06-19 | — | Tüm metrik ve parametrelere tooltip (help) eklendi; Terimler Sözlüğü ve Sütun Açıklamaları expander'ları eklendi |
| 2026-06-19 | — | Stres testi 10 kurala çıkarıldı, konsantrasyon riski, rotasyon analizi, kombinasyon kuralları eklendi |
| 2026-06-18 | — | Mevsimsel takvim, akıllı yorum, 4-metrik dashboard, mevsimsel mod, Excel export eklendi |
| 2026-06-18 | — | money_flow.py eklendi, app.py'ye para akışı analizi UI'ı entegre edildi |
| 2026-06-18 öncesi | cdee046 | Stress test modülü eklendi |
| 2026-06-18 öncesi | 00f5742 | pytefas eklendi |
| 2026-06-18 öncesi | aa1fa75 | TEFAS kapalıyken hata düzeltmesi |
| 2026-06-18 öncesi | 5a7e2f1 | Streamlit app eklendi |
