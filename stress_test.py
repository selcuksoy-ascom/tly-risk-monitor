# =============================================================================
# stress_test.py - Stres Testi & Fon Sagligi Modulu
# =============================================================================
# TEFAS verisi + Fonoloji holdings ile nakit tamponu, yatirimci kacisi,
# AUM erimesi, NAV trendi ve birlesik stres analizi yapar.
# Hata durumunda sessizce None doner, diger moduller etkilenmez.
# =============================================================================

from datetime import date, timedelta
from typing import Optional, Dict, Any
import urllib.request
import json

import pandas as pd

FUND_CODE = "TLY"
FUND_KIND = "YAT"
HISTORY_DAYS = 50

# Uyari esikleri
CASH_BUFFER_CRITICAL = 10.0       # %10 alti kritik
INVESTOR_DROP_WARNING = -1.0      # %1 dusus uyari
INVESTOR_DROP_CRITICAL = -3.0     # %3 dusus kritik
AUM_DROP_WARNING = -2.0           # %2 dusus uyari
AUM_DROP_CRITICAL = -5.0          # %5 dusus kritik
NAV_CONSECUTIVE_DAYS = 5


def _fetch_tefas_data() -> Optional[pd.DataFrame]:
    """TLY fonunun son 30 gunluk TEFAS verisini ceker."""
    try:
        from pytefas import Crawler
    except ImportError:
        return None

    try:
        c = Crawler()
        end = date.today()
        start = end - timedelta(days=HISTORY_DAYS + 10)
        df = c.fetch(
            start.isoformat(),
            end.isoformat(),
            kind=FUND_KIND,
            fund_code=FUND_CODE,
        )
        if df is None or df.empty:
            return None
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None


def _fetch_holdings() -> Optional[Dict[str, Any]]:
    """Fonoloji API'den TLY holdings verisini ceker."""
    try:
        from config import FONOLOJI_API_KEY
    except ImportError:
        return None

    if not FONOLOJI_API_KEY:
        return None

    try:
        url = "https://fonoloji.com/v1/funds/TLY/holdings"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {FONOLOJI_API_KEY}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _calc_repo_ratio(holdings: Dict[str, Any]) -> Optional[float]:
    """Holdings icindeki ters repo oranini hesapla (asset_type == 'repo' weight toplami)."""
    try:
        items = holdings.get("data", holdings) if isinstance(holdings, dict) else []
        if isinstance(items, dict):
            items = items.get("holdings", items.get("items", []))
        if not isinstance(items, list):
            return None

        repo_weight = 0.0
        for item in items:
            if not isinstance(item, dict):
                continue
            asset_type = item.get("asset_type", item.get("type", ""))
            if isinstance(asset_type, str) and asset_type.lower() == "repo":
                weight = item.get("weight", item.get("ratio", 0))
                repo_weight += float(weight)

        return repo_weight
    except Exception:
        return None


def _pct_change(series: pd.Series, lookback: int) -> Optional[float]:
    """Belirtilen gun kadar geriye gore % degisim."""
    clean = series.dropna()
    if len(clean) < max(2, lookback + 1):
        return None
    recent = clean.iloc[-1]
    base = clean.iloc[-(lookback + 1)]
    if base == 0:
        return None
    return round(((recent - base) / base) * 100.0, 2)


def _consecutive_down(series: pd.Series, n: int) -> bool:
    """Serinin son n degeri art arda azalmis mi?"""
    vals = series.dropna()
    if len(vals) < n + 1:
        return False
    window = vals.iloc[-(n + 1):]
    return all(window.iloc[i] > window.iloc[i + 1] for i in range(len(window) - 1))


def analyze_stress_test() -> Optional[Dict[str, Any]]:
    """
    Stres testi ve fon sagligi analizi yapar.

    Returns:
        dict veya None (hata / veri yoksa):
        {
            'nav': float,
            'nav_change': float,
            'aum': float,
            'aum_change_7d': float,
            'investor_count': int,
            'investor_change_7d': float,
            'repo_ratio': float,
            'cash_buffer': float,
            'coverable_exit': float,
            'nav_down_5d': bool,
            'nav_trend': str,          # 'up', 'down', 'flat'
            'stress_level': str,       # 'low', 'medium', 'high'
            'warnings': list[str],
        }
    """
    df = _fetch_tefas_data()
    if df is None or df.empty:
        return None

    try:
        price_col = "price"
        aum_col = "portfolio_size"
        inv_col = "investor_count"

        valid_df = df[df[price_col] > 0].copy()
        if valid_df.empty:
            return None

        latest_valid = valid_df.iloc[-1]
        nav = float(latest_valid[price_col])
        aum = float(latest_valid[aum_col])

        latest = df.iloc[-1]
        inv = int(latest[inv_col]) if pd.notna(latest[inv_col]) else None

        # Gunluk NAV degisimi
        nav_series = valid_df[price_col]
        nav_change = None
        if len(nav_series) >= 2:
            n0 = nav_series.iloc[-1]
            n1 = nav_series.iloc[-2]
            if n1 != 0:
                nav_change = round(((n0 - n1) / n1) * 100.0, 2)

        # 7 gunluk degisimler
        inv_change_7d = _pct_change(df[inv_col], 7)
        aum_change_7d = _pct_change(valid_df[aum_col], 7)

        # NAV 5 gunluk art arda dusus
        nav_down_5d = _consecutive_down(valid_df[price_col], NAV_CONSECUTIVE_DAYS)

        # NAV trend (son 5 vs onceki 5)
        nav_trend = "flat"
        if len(valid_df) >= 10:
            recent_5 = valid_df[price_col].iloc[-5:].mean()
            prev_5 = valid_df[price_col].iloc[-10:-5].mean()
            if prev_5 > 0:
                diff = (recent_5 - prev_5) / prev_5
                if diff > 0.002:
                    nav_trend = "up"
                elif diff < -0.002:
                    nav_trend = "down"

        # ---- Fonoloji holdings cek ----
        holdings = _fetch_holdings()
        repo_ratio = _calc_repo_ratio(holdings) if holdings else None

        # ---- Hesaplamalar ----
        cash_buffer = None
        coverable_exit = None
        if repo_ratio is not None and aum is not None:
            cash_buffer = (repo_ratio / 100.0) * aum if repo_ratio > 0 else 0.0
            coverable_exit = repo_ratio

        # ---- Uyari kurallari ----
        warnings = []
        triggered_rules = 0

        # KURAL 1 - Nakit Tamponu
        if coverable_exit is not None and coverable_exit < CASH_BUFFER_CRITICAL:
            warnings.append(
                f"🚨 KRITIK: Nakit tamponu yetersiz, "
                f"yatirimcilarin %{coverable_exit:.1f}'i cikmak isterse hisse satilmak zorunda"
            )
            triggered_rules += 1

        # KURAL 2 - Yatirimci Kacisi
        if inv_change_7d is not None:
            if inv_change_7d < INVESTOR_DROP_CRITICAL:
                warnings.append("🚨 KRITIK: Fondan yatirimci cikisi hizlaniyor")
                triggered_rules += 1
            elif inv_change_7d < INVESTOR_DROP_WARNING:
                warnings.append("⚠️ UYARI: Yatirimci sayisi azaliyor")
                triggered_rules += 1

        # KURAL 3 - AUM Erimesi
        if aum_change_7d is not None:
            if aum_change_7d < AUM_DROP_CRITICAL:
                warnings.append("🚨 KRITIK: Fon buyuklugu hizla eriyor")
                triggered_rules += 1
            elif aum_change_7d < AUM_DROP_WARNING:
                warnings.append("⚠️ UYARI: Fon buyuklugu azaliyor")
                triggered_rules += 1

        # KURAL 4 - NAV Trend
        if nav_down_5d:
            warnings.append("⚠️ UYARI: NAV 5 gundur dusuyor")
            triggered_rules += 1

        # KURAL 5 - Birlesik Stres
        if triggered_rules >= 2:
            warnings.append("🚨 SISTEMIK STRES: Birden fazla risk gostergesi ayni anda alarm veriyor")

        # Stres seviyesi
        has_critical = any("KRITIK" in w for w in warnings)
        has_warning = any("UYARI" in w for w in warnings)
        if has_critical:
            stress_level = "high"
        elif has_warning:
            stress_level = "medium"
        else:
            stress_level = "low"

        return {
            "nav": nav,
            "nav_change": nav_change,
            "aum": aum,
            "aum_change_7d": aum_change_7d,
            "investor_count": inv,
            "investor_change_7d": inv_change_7d,
            "repo_ratio": repo_ratio,
            "cash_buffer": cash_buffer,
            "coverable_exit": coverable_exit,
            "nav_down_5d": nav_down_5d,
            "nav_trend": nav_trend,
            "stress_level": stress_level,
            "warnings": warnings,
        }
    except Exception:
        return None
