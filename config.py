# =============================================================================
# config.py - TLY Portföy Sabitleri
# =============================================================================
# KULLANIM: Her ay KAP raporuna göre ağırlıkları güncelleyin.
# Son güncelleme: 2 Temmuz 2026 (Haziran 2026 KAP raporu)
# =============================================================================

PORTFOLIO = {
    "DSTKF.IS": {
        "name": "Destek Faktoring",
        "weight": 22.84,
        "category": "anchor",
        "prev_weight": 17.71,
    },
    "OZATD.IS": {
        "name": "Ozata Denizcilik",
        "weight": 14.29,
        "category": "anchor",
        "prev_weight": 17.16,
    },
    "PEKGY.IS": {
        "name": "Peker GYO",
        "weight": 7.73,
        "category": "anchor",
        "prev_weight": 9.89,
    },
    "TEHOL.IS": {
        "name": "Tera Teknoloji",
        "weight": 7.13,
        "category": "group",
        "prev_weight": 5.50,
    },
    "TERA.IS": {
        "name": "Tera Yatirim",
        "weight": 6.63,
        "category": "group",
        "prev_weight": 11.50,
    },
    "TRHOL.IS": {
        "name": "Tera Finansal",
        "weight": 5.61,
        "category": "group",
        "prev_weight": 6.59,
    },
    "ANELE.IS": {
        "name": "Anel Elektrik",
        "weight": 1.99,
        "category": "anchor",
        "prev_weight": 2.15,
    },
    "SELEC.IS": {
        "name": "Selcuk Ecza",
        "weight": 1.04,
        "category": "anchor",
        "prev_weight": 0.00,
    },
    "ALKLC.IS": {
        "name": "Altinkilic Gida",
        "weight": 0.53,
        "category": "anchor",
        "prev_weight": 0.66,
    },
    "SVGYO.IS": {
        "name": "Savur GYO",
        "weight": 0.52,
        "category": "anchor",
        "prev_weight": 0.55,
    },
    "HEDEF.IS": {
        "name": "Hedef Holding",
        "weight": 0.27,
        "category": "anchor",
        "prev_weight": 0.28,
    },
    "MANAS.IS": {
        "name": "Manas Enerji",
        "weight": 0.14,
        "category": "anchor",
        "prev_weight": 0.00,
    },
    "TMPOL.IS": {
        "name": "Temapol Polimer",
        "weight": 0.01,
        "category": "anchor",
        "prev_weight": 0.33,
    },
    "EUPWR.IS": {
        "name": "Europower Enerji",
        "weight": 0.01,
        "category": "anchor",
        "prev_weight": 0.03,
    },
}

# Fonun toplam hisse oranı (%), geri kalan nakit/tahvil gibi sabit varlıklardır
EQUITY_RATIO = 68.74

# Varsayılan sermaye (TL)
DEFAULT_CAPITAL = 500_000

# Günlük panik senaryosu kayıp oranı (%)
PANIC_RATE = 10.0

# Sistemik risk için izlenen grup hisseleri (KURAL 3)
GROUP_TICKERS = ["TERA.IS", "TRHOL.IS", "TEHOL.IS"]

# Korelasyon eşiği - bu değerin üzerinde ise sistemik risk uyarısı
CORRELATION_THRESHOLD = 0.80

# Likidite kilitlenmesi için hacim eşiği (30 günlük ortalamanın yüzdesi)
VOLUME_LOCKDOWN_THRESHOLD = 0.50  # %50 altı

# Sığ piyasa uyarısı için hacim eşiği (30 günlük ortalamanın yüzdesi)
VOLUME_THIN_MARKET_THRESHOLD = 0.20  # %20 altı → fiyat yönü bağımsız uyarı

# Ağırlık eşiği (KURAL 1 için, % cinsinden)
WEIGHT_THRESHOLD = 10.0

# Fiyat düşüş eşiği (KURAL 1 için, % cinsinden, negatif)
PRICE_DROP_THRESHOLD = -5.0

# Veri çekme için geçmiş gün sayısı
HISTORY_DAYS = 30

# Fonoloji API anahtarı (https://fonoloji.com)
FONOLOJI_API_KEY = "fon_PT3alvQwy3575dlOUTvytHigzFKyBJnF"
