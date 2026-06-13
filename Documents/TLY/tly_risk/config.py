# =============================================================================
# config.py - TLY Portföy Sabitleri
# =============================================================================
# KULLANIM: Her ay KAP raporuna göre ağırlıkları güncelleyin.
# Son güncelleme: 8 Haziran 2026
# =============================================================================

PORTFOLIO = {
    "DSTKF.IS": {
        "name": "Destek Faktoring",
        "weight": 17.71,
        "category": "anchor",
        "prev_weight": 17.71,  # Önceki aya ait ağırlık (rotasyon tespiti için)
    },
    "OZATD.IS": {
        "name": "Ozata Denizcilik",
        "weight": 17.16,
        "category": "anchor",
        "prev_weight": 17.16,
    },
    "TERA.IS": {
        "name": "Tera Yatirim",
        "weight": 11.50,
        "category": "group",
        "prev_weight": 11.50,
    },
    "PEKGY.IS": {
        "name": "Peker GYO",
        "weight": 9.89,
        "category": "other",
        "prev_weight": 9.89,
    },
    "TRHOL.IS": {
        "name": "Tera Finansal",
        "weight": 6.59,
        "category": "group",
        "prev_weight": 6.59,
    },
    "TEHOL.IS": {
        "name": "Tera Teknoloji",
        "weight": 5.50,
        "category": "group",
        "prev_weight": 5.50,
    },
    "UKA.IS": {
        "name": "Uka GYF",
        "weight": 12.84,
        "category": "other",
        "prev_weight": 12.84,
    },
}

# Fonun toplam hisse oranı (%), geri kalan nakit/tahvil gibi sabit varlıklardır
EQUITY_RATIO = 71.54

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

# Ağırlık eşiği (KURAL 1 için, % cinsinden)
WEIGHT_THRESHOLD = 10.0

# Fiyat düşüş eşiği (KURAL 1 için, % cinsinden, negatif)
PRICE_DROP_THRESHOLD = -5.0

# Veri çekme için geçmiş gün sayısı
HISTORY_DAYS = 30
