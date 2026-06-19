# =============================================================================
# rotation_tracker.py - Rotasyon Analizi Modulu
# =============================================================================
# Fonoloji holdings API'sinden aylik gecmis veriyi ceker, hisse agirlik
# degisimlerini analiz eder, rotasyon tespiti ve sig hisse havuzu takibi yapar.
# Hata durumunda sessizce None doner, diger moduller etkilenmez.
# =============================================================================

from datetime import date, timedelta
from typing import Optional, Dict, Any, List
import urllib.request
import json
import calendar

import pandas as pd

# Izlenen sig hisse havuzu
SHALLOW_POOL = ["DSTKF.IS", "OZATD.IS", "TEHOL.IS", "TRHOL.IS", "PEKGY.IS"]
ROTATION_THRESHOLD_PP = 10.0  # agirlikta >10 puan degisim → rotasyon
PAIR_TOLERANCE = 0.30  # rotasyon cifti icin ±%30 tolerans
LOOKBACK_MONTHS = 6


def _get_month_end_dates(months_back: int = LOOKBACK_MONTHS) -> List[str]:
    """Son N ayin son gununu 'YYYY-MM-DD' formatinda dondurur."""
    today = date.today()
    dates = []
    for i in range(months_back):
        # i ay onceki ayin 1'i
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        last_day = calendar.monthrange(year, month)[1]
        dates.append(f"{year}-{month:02d}-{last_day:02d}")
    return dates


def _fetch_holdings_for_date(report_date: str) -> Optional[Dict[str, Any]]:
    """Belirli bir tarih icin Fonoloji holdings verisi ceker."""
    try:
        from config import FONOLOJI_API_KEY
    except ImportError:
        return None

    if not FONOLOJI_API_KEY:
        return None

    try:
        url = f"https://fonoloji.com/v1/funds/TLY/holdings?report_date={report_date}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {FONOLOJI_API_KEY}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _extract_stock_weights(holdings: Dict[str, Any]) -> Dict[str, float]:
    """Holdings JSON'dan hisse senedi agirliklarini cikarir."""
    try:
        items = holdings.get("data", holdings) if isinstance(holdings, dict) else []
        if isinstance(items, dict):
            items = items.get("holdings", items.get("items", []))
        if not isinstance(items, list):
            return {}

        weights = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            asset_type = item.get("asset_type", item.get("type", ""))
            if not isinstance(asset_type, str):
                continue
            if asset_type.lower() in ("stock", "hisse", "equity"):
                ticker = item.get("ticker", item.get("code", item.get("symbol", "")))
                weight = item.get("weight", item.get("ratio", 0))
                if ticker and weight:
                    weights[ticker] = float(weight)
        return weights
    except Exception:
        return {}


def analyze_rotation() -> Optional[Dict[str, Any]]:
    """
    Son 6 aylik Fonoloji holdings verisini kullanarak rotasyon analizi yapar.

    Returns:
        {
            'monthly_weights': [{'report_date': str, 'weights': dict}],
            'rotations': [{'month': str, 'stock': str, 'from_weight': float,
                           'to_weight': float, 'change_pp': float}],
            'rotation_pairs': [{'month': str, 'stock_a': str, 'stock_b': str,
                                'delta_a': float, 'delta_b': float}],
            'pool': {
                'total': int,
                'used': int,
                'remaining': int,
                'peaks': [{'stock': str, 'month': str, 'weight': float}],
                'fresh': [str],
            },
            'pool_warning': str or None,
            'last_month': str,
        }
    """
    month_ends = _get_month_end_dates(LOOKBACK_MONTHS)

    # Her ay icin holdings cek
    monthly_data = []
    for me_str in month_ends:
        holdings = _fetch_holdings_for_date(me_str)
        if holdings is not None:
            weights = _extract_stock_weights(holdings)
            if weights:
                monthly_data.append({
                    "report_date": me_str,
                    "weights": weights,
                })

    if len(monthly_data) < 2:
        return None

    # Tarihe gore sirala (eskiden yeniye)
    monthly_data.sort(key=lambda x: x["report_date"])

    # ---- Rotasyon tespiti ----
    rotations = []
    rotation_pairs = []

    for i in range(1, len(monthly_data)):
        prev_w = monthly_data[i - 1]["weights"]
        curr_w = monthly_data[i]["weights"]
        month_label = monthly_data[i]["report_date"][:7]  # YYYY-MM

        # Tum hisseleri topla
        all_stocks = set(list(prev_w.keys()) + list(curr_w.keys()))

        # Degisimleri hesapla
        changes = {}
        for stock in all_stocks:
            pw = prev_w.get(stock, 0)
            cw = curr_w.get(stock, 0)
            if pw > 0 or cw > 0:
                changes[stock] = cw - pw

        # Hizli rotasyon: >10 puan degisim
        for stock, delta in changes.items():
            if abs(delta) > ROTATION_THRESHOLD_PP:
                rotations.append({
                    "month": month_label,
                    "stock": stock,
                    "from_weight": round(prev_w.get(stock, 0), 2),
                    "to_weight": round(curr_w.get(stock, 0), 2),
                    "change_pp": round(delta, 2),
                })

        # Rotasyon cifti: biri azalirken digeri benzer oranda artiyor
        losers = [(s, d) for s, d in changes.items() if d < 0]
        gainers = [(s, d) for s, d in changes.items() if d > 0]

        for ls, ld in losers:
            for gs, gd in gainers:
                # Benzer buyuklukte mi? (±%30 tolerans)
                if abs(ld) > 2.0 and abs(gd) > 2.0:
                    ratio = abs(gd) / abs(ld) if abs(ld) > 0 else 999
                    if 1.0 - PAIR_TOLERANCE <= ratio <= 1.0 + PAIR_TOLERANCE:
                        rotation_pairs.append({
                            "month": month_label,
                            "stock_a": ls,
                            "stock_b": gs,
                            "delta_a": round(ld, 2),
                            "delta_b": round(gd, 2),
                        })

    # ---- Havuz analizi ----
    # Son 6 ayda her havuz hissesinin ulastigi en yuksek agirlik
    pool_peaks = {}
    for entry in monthly_data:
        month_label = entry["report_date"][:7]
        for stock in SHALLOW_POOL:
            w = entry["weights"].get(stock, 0)
            if stock not in pool_peaks or w > pool_peaks[stock]["weight"]:
                pool_peaks[stock] = {"month": month_label, "weight": w}

    # Zirve yapanlar (agirligi >0 olanlar)
    peaked = []
    fresh = []
    for stock in SHALLOW_POOL:
        if stock in pool_peaks and pool_peaks[stock]["weight"] > 0:
            peaked.append({
                "stock": stock,
                "month": pool_peaks[stock]["month"],
                "weight": round(pool_peaks[stock]["weight"], 2),
            })
        else:
            fresh.append(stock)

    # Havuz uyarisi
    pool_warning = None
    used_count = len(peaked)
    remaining_count = len(fresh)
    if remaining_count < 2:
        pool_warning = "⚠️ Rotasyon edilecek yeni hisse secenegi azaliyor"

    pool = {
        "total": len(SHALLOW_POOL),
        "used": used_count,
        "remaining": remaining_count,
        "peaks": peaked,
        "fresh": fresh,
    }

    return {
        "monthly_weights": monthly_data,
        "rotations": rotations,
        "rotation_pairs": rotation_pairs,
        "pool": pool,
        "pool_warning": pool_warning,
        "last_month": monthly_data[-1]["report_date"][:7] if monthly_data else None,
    }
