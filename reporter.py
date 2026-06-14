# =============================================================================
# reporter.py - Terminal Rapor Formatı
# =============================================================================
# colorama ile renkli çıktı, tabulate ile tablo formatı.
# =============================================================================

from datetime import date
from typing import Dict, Any, List, Optional
from tabulate import tabulate
from colorama import init, Fore, Style, Back

# Colorama başlat (Windows için autoreset=True)
init(autoreset=True)

# ---------------------------------------------------------------------------
# Config import (eşik değeri için)
# ---------------------------------------------------------------------------
try:
    from config import CORRELATION_THRESHOLD as CORRELATION_THRESHOLD_DISPLAY
except ImportError:
    CORRELATION_THRESHOLD_DISPLAY = 0.80

# ---------------------------------------------------------------------------
# Renk Sabitleri
# ---------------------------------------------------------------------------
C_RED    = Fore.RED + Style.BRIGHT
C_YELLOW = Fore.YELLOW + Style.BRIGHT
C_GREEN  = Fore.GREEN + Style.BRIGHT
C_CYAN   = Fore.CYAN + Style.BRIGHT
C_WHITE  = Fore.WHITE + Style.BRIGHT
C_RESET  = Style.RESET_ALL
C_BOLD   = Style.BRIGHT

BOX_WIDTH = 54


# ---------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# ---------------------------------------------------------------------------

def _box_line(text: str, width: int = BOX_WIDTH) -> str:
    """Metni kutu içinde ortalar."""
    padded = text.center(width - 2)
    return f"║{padded}║"


def _fmt_pct(value: Optional[float], sign: bool = True) -> str:
    """Yüzdeyi formatla."""
    if value is None:
        return "N/A"
    sign_str = "+" if sign and value > 0 else ""
    return f"{sign_str}{value:.1f}%"


def _fmt_tl(value: float) -> str:
    """TL değerini Türkçe formatla."""
    return f"{value:>12,.0f} TL".replace(",", ".")


def _color_change(change_pct: Optional[float]) -> str:
    """Değişim yüzdesini renklendir."""
    if change_pct is None:
        return "  N/A  "
    txt = f"{change_pct:+.1f}%"
    if change_pct < -5.0:
        return C_RED + txt + C_RESET
    elif change_pct < 0:
        return Fore.RED + txt + C_RESET
    elif change_pct > 0:
        return C_GREEN + txt + C_RESET
    return txt


def _color_status(status: str, is_critical: bool, is_rotation: bool, is_thin_market: bool = False) -> str:
    """Likidite durumunu renklendir."""
    if is_critical:
        return C_RED + "KRİTİK ⚠️" + C_RESET
    elif is_rotation:
        return C_CYAN + "ROTASYON ↩" + C_RESET
    elif is_thin_market:
        return C_YELLOW + "SIĞ PİYASA ⚠️" + C_RESET
    elif status == "VERİ YOK":
        return C_YELLOW + "VERİ YOK" + C_RESET
    else:
        return C_GREEN + "Normal ✓" + C_RESET


# ---------------------------------------------------------------------------
# Başlık
# ---------------------------------------------------------------------------

def print_header(report_date: Optional[date] = None) -> None:
    """Dekoratif başlık kutusu yazdır."""
    if report_date is None:
        report_date = date.today()

    date_str = report_date.strftime("%Y-%m-%d")
    title = f"TLY RİSK RAPORU - {date_str}"

    print()
    print(C_CYAN + "╔" + "═" * BOX_WIDTH + "╗" + C_RESET)
    print(C_CYAN + _box_line("") + C_RESET)
    print(C_CYAN + C_BOLD + _box_line(title) + C_RESET)
    print(C_CYAN + _box_line("Tera Portföy Birinci Serbest Fon") + C_RESET)
    print(C_CYAN + _box_line("") + C_RESET)
    print(C_CYAN + "╚" + "═" * BOX_WIDTH + "╝" + C_RESET)


# ---------------------------------------------------------------------------
# Risk Skoru Tablosu
# ---------------------------------------------------------------------------

def print_risk_table(per_stock: Dict[str, Dict[str, Any]]) -> None:
    """Hisse bazlı risk tablosunu yazdır."""
    print()
    print(C_WHITE + "[ RİSK SKORU TABLOSU ]" + C_RESET)

    headers = ["Ticker", "Ad", "Ağırlık", "Fiyat", "Değ%", "Hacim/Ort", "Lik.Durumu"]
    rows = []

    for ticker, data in per_stock.items():
        short_ticker = ticker.replace(".IS", "")
        name = data.get("name", "?")[:18]
        weight = f"%{data['weight']:.2f}"

        price = data.get("price")
        price_str = f"{price:.4f}" if price is not None else "N/A"

        change_pct = data.get("change_pct")
        change_str = _fmt_pct(change_pct, sign=True) if change_pct is not None else "N/A"

        vol_ratio = data.get("volume_ratio")
        vol_str = f"%{vol_ratio:.0f}" if vol_ratio is not None else "N/A"

        is_critical = data.get("is_critical", False)
        is_rotation = data.get("is_rotation", False)
        is_thin = data.get("is_thin_market", False)
        liq_status = data.get("liquidity_status", "Normal")

        # Satır rengi
        if is_critical:
            row_color = C_RED
        elif is_rotation:
            row_color = C_CYAN
        elif is_thin:
            row_color = C_YELLOW
        elif change_pct is not None and change_pct < 0:
            row_color = Fore.YELLOW
        else:
            row_color = ""

        status_display = _color_status(liq_status, is_critical, is_rotation, data.get("is_thin_market", False))

        rows.append([
            row_color + short_ticker + C_RESET,
            row_color + name + C_RESET,
            weight,
            price_str,
            row_color + change_str + C_RESET if row_color else change_str,
            vol_str,
            status_display,
        ])

    print(tabulate(rows, headers=headers, tablefmt="simple", colalign=("left",) * 7))


# ---------------------------------------------------------------------------
# Sistemik Risk Bölümü
# ---------------------------------------------------------------------------

def print_systemic_risk(systemic: Dict[str, Any]) -> None:
    """Grup korelasyonu ve sistemik risk bilgisini yazdır."""
    print()
    print(C_WHITE + "[ SİSTEMİK RİSK ]" + C_RESET)

    corr = systemic.get("correlation")
    is_critical = systemic.get("is_critical", False)
    msg = systemic.get("message", "")
    tickers = systemic.get("tickers", [])

    tickers_short = "/".join(t.replace(".IS", "") for t in tickers)

    if corr is None:
        print(f"  Grup Korelasyonu ({tickers_short}): " +
              C_YELLOW + "Hesaplanamadı" + C_RESET)
        return

    corr_str = f"{corr:.2f}"

    if is_critical:
        corr_display = C_RED + corr_str + C_RESET
        arrow = C_RED + " → ⚠️  YÜKSEK (SİSTEMİK RİSK)" + C_RESET
    elif corr > CORRELATION_THRESHOLD_DISPLAY:
        corr_display = C_YELLOW + corr_str + C_RESET
        arrow = C_YELLOW + " → ⚠️  YÜKSEK (henüz kritik değil)" + C_RESET
    else:
        corr_display = C_GREEN + corr_str + C_RESET
        arrow = C_GREEN + " → Normal" + C_RESET

    print(f"  Grup Korelasyonu ({tickers_short}): {corr_display}{arrow}")


# ---------------------------------------------------------------------------
# T+2 Simülasyon Raporu
# ---------------------------------------------------------------------------

def print_simulation(sim: Dict[str, Any]) -> None:
    """T+2 simülasyon sonuçlarını yazdır."""
    print()
    print(C_WHITE + "[ T+2 VALÖR SİMÜLATÖRÜ ]" + C_RESET)

    capital = sim["capital"]
    equity_vals = sim["daily_equity_values"]
    panic = sim["panic_rate"]
    loss_tl = sim["equity_loss_tl"]
    loss_pct = sim["equity_loss_pct"]
    remaining = sim["remaining_portfolio"]

    lines = [
        ("Anapara", _fmt_tl(capital)),
        ("Hisse Portföyü (Gün 0)", _fmt_tl(equity_vals[0])),
    ]

    for i in range(1, len(equity_vals)):
        label = f"Gün {i} Değer (T+{i})"
        val_str = _fmt_tl(equity_vals[i]) + f"  (-%{panic:.0f}/gün)"
        lines.append((label, val_str))

    lines.append(("", ""))  # Boş satır

    loss_str = f"{loss_tl:>12,.0f} TL  (%{loss_pct:.1f})".replace(",", ".")
    remaining_str = _fmt_tl(remaining)

    lines.append(("Toplam Hisse Kaybı", C_RED + loss_str + C_RESET))
    lines.append(("Kalan Toplam Portföy", C_YELLOW + remaining_str + C_RESET))

    for label, value in lines:
        if label:
            print(f"  {label:<28}: {value}")
        else:
            print()


# ---------------------------------------------------------------------------
# Kritik Uyarılar
# ---------------------------------------------------------------------------

def print_critical_alerts(critical_alerts: List[str], rotation_logs: List[str], thin_market_alerts: List[str] = None) -> None:
    """Kritik uyarıları, rotasyon loglarını ve sığ piyasa uyarılarını yazdır."""
    print()
    print(C_WHITE + "[ UYARILAR & LOGLAR ]" + C_RESET)

    if not critical_alerts and not rotation_logs and not thin_market_alerts:
        print(C_GREEN + "  ✓  Bugün için kritik uyarı yok." + C_RESET)
        return

    if critical_alerts:
        print(C_RED + "  KRİTİK UYARILAR:" + C_RESET)
        for alert in critical_alerts:
            print(C_RED + f"  ⚠️   {alert}" + C_RESET)

    if thin_market_alerts:
        print()
        print(C_YELLOW + "  SIĞ PİYASA UYARILARI:" + C_RESET)
        for alert in thin_market_alerts:
            print(C_YELLOW + f"  ⚠️   {alert}" + C_RESET)

    if rotation_logs:
        print()
        print(C_CYAN + "  ROTASYON LOGLARI (alarm yok):" + C_RESET)
        for log in rotation_logs:
            print(C_CYAN + f"  ↩   {log}" + C_RESET)


# ---------------------------------------------------------------------------
# Alt Bilgi
# ---------------------------------------------------------------------------

def print_footer() -> None:
    """Rapor sonu bilgisi."""
    print()
    print(C_CYAN + "─" * (BOX_WIDTH + 2) + C_RESET)
    print(C_CYAN + "  TLY Risk Analiz Aracı  |  config.py'yi aylık güncelleyin." + C_RESET)
    print(C_CYAN + "─" * (BOX_WIDTH + 2) + C_RESET)
    print()


# (CORRELATION_THRESHOLD_DISPLAY dosya başında tanımlandı)
