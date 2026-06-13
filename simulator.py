# =============================================================================
# simulator.py - T+2 Valör Simülatörü
# =============================================================================
# Panik senaryosunda 2 gün boyunca kümülatif kayıpları hesaplar.
# Hisse dışı (nakit/tahvil) kısım sabit tutulur.
# =============================================================================

from typing import Dict, Any
from config import EQUITY_RATIO, DEFAULT_CAPITAL, PANIC_RATE


def run_simulation(
    capital: float = DEFAULT_CAPITAL,
    equity_ratio: float = EQUITY_RATIO,
    panic_rate: float = PANIC_RATE,
    days: int = 2,
) -> Dict[str, Any]:
    """
    T+2 Valör Simülasyonunu çalıştırır.

    Args:
        capital       : Toplam anapara (TL)
        equity_ratio  : Hisse oranı (%, 0-100 arası)
        panic_rate    : Günlük kayıp senaryosu (%, pozitif değer gir)
        days          : Simülasyon gün sayısı (varsayılan: 2)

    Returns:
        dict: Simülasyon sonuçları
    """
    # Hisse portföy değeri (Gün 0)
    equity_value_day0 = capital * (equity_ratio / 100.0)

    # Hisse dışı kısım (nakit, tahvil - sabit tutulur)
    non_equity_value = capital - equity_value_day0

    # Günlük kayıp çarpanı
    daily_multiplier = 1.0 - (panic_rate / 100.0)

    # Her gün için hisse değerini hesapla
    daily_values = [equity_value_day0]
    for day in range(1, days + 1):
        next_value = daily_values[-1] * daily_multiplier
        daily_values.append(next_value)

    # Net kayıp
    final_equity = daily_values[-1]
    equity_loss_tl = final_equity - equity_value_day0
    equity_loss_pct = (equity_loss_tl / equity_value_day0) * 100.0 if equity_value_day0 > 0 else 0.0

    # Kalan toplam portföy (hisse dışı sabit)
    remaining_portfolio = final_equity + non_equity_value

    return {
        "capital": capital,
        "equity_ratio": equity_ratio,
        "panic_rate": panic_rate,
        "non_equity_value": round(non_equity_value, 2),
        "daily_equity_values": [round(v, 2) for v in daily_values],
        "equity_loss_tl": round(equity_loss_tl, 2),
        "equity_loss_pct": round(equity_loss_pct, 2),
        "remaining_portfolio": round(remaining_portfolio, 2),
        "days": days,
    }


def format_tl(value: float) -> str:
    """TL değerini okunabilir formata çevirir."""
    return f"{value:,.0f} TL".replace(",", ".")


def get_capital_from_user() -> float:
    """
    Kullanıcıdan sermaye miktarını alır.
    Enter'a basılırsa varsayılan değer kullanılır.
    """
    print(f"\n  Anapara miktarını girin (Enter = {DEFAULT_CAPITAL:,} TL): ", end="")
    raw = input().strip()

    if not raw:
        return float(DEFAULT_CAPITAL)

    # Binlik ayraç ve TL sembolü temizle
    cleaned = raw.replace(".", "").replace(",", "").replace("TL", "").replace(" ", "")

    try:
        value = float(cleaned)
        if value <= 0:
            print(f"  [UYARI] Geçersiz değer. Varsayılan kullanılıyor: {DEFAULT_CAPITAL:,} TL")
            return float(DEFAULT_CAPITAL)
        return value
    except ValueError:
        print(f"  [UYARI] Sayı okunamadı. Varsayılan kullanılıyor: {DEFAULT_CAPITAL:,} TL")
        return float(DEFAULT_CAPITAL)
