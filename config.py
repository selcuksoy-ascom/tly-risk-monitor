# =============================================================================
# config.py - TLY Portföy Sabitleri
# =============================================================================
# KULLANIM: Her ay KAP raporuna göre ağırlıkları güncelleyin.
# Son güncelleme: 20 Haziran 2026
# =============================================================================

PORTFOLIO = {
    "DSTKF.IS": {
        "name": "Destek Faktoring",
        "weight": 17.71,
        "category": "anchor",
        "prev_weight": 23.60,
    },
    "OZATD.IS": {
        "name": "Ozata Denizcilik",
        "weight": 17.16,
        "category": "anchor",
        "prev_weight": 1.29,
    },
    "TERA.IS": {
        "name": "Tera Yatirim",
        "weight": 11.50,
        "category": "group",
        "prev_weight": 12.86,
    },
    "PEKGY.IS": {
        "name": "Peker GYO",
        "weight": 9.89,
        "category": "anchor",
        "prev_weight": 8.51,
    },
    "TRHOL.IS": {
        "name": "Tera Finansal",
        "weight": 6.59,
        "category": "group",
        "prev_weight": 5.98,
    },
    "TEHOL.IS": {
        "name": "Tera Teknoloji",
        "weight": 5.50,
        "category": "group",
        "prev_weight": 2.25,
    },
    "ANELE.IS": {
        "name": "Anel Elektrik",
        "weight": 2.15,
        "category": "anchor",
        "prev_weight": 2.15,
    },
    "ALKLC.IS": {
        "name": "Altinkilic Gida",
        "weight": 0.66,
        "category": "anchor",
        "prev_weight": 0.70,
    },
    "SVGYO.IS": {
        "name": "Savur GYO",
        "weight": 0.55,
        "category": "anchor",
        "prev_weight": 0.32,
    },
    "TMPOL.IS": {
        "name": "Temapol Polimer",
        "weight": 0.33,
        "category": "anchor",
        "prev_weight": 0.40,
    },
    "HEDEF.IS": {
        "name": "Hedef Holding",
        "weight": 0.28,
        "category": "anchor",
        "prev_weight": 0.32,
    },
    "CWENE.IS": {
        "name": "CW Enerji",
        "weight": 0.03,
        "category": "anchor",
        "prev_weight": 0.07,
    },
    "EUPWR.IS": {
        "name": "Europower Enerji",
        "weight": 0.03,
        "category": "anchor",
        "prev_weight": 0.03,
    },
}

# Fonun toplam hisse oranı (%), geri kalan nakit/tahvil gibi sabit varlıklardır
EQUITY_RATIO = 72.38

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
