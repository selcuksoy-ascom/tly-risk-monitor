# =============================================================================
# tefas_fetcher.py - TEFAS Fon Verisi Çekme Modülü
# =============================================================================
# pytefas ile TLY fonunun NAV, AUM ve yatırımcı sayısını çeker,
# eğilim bazlı uyarılar üretir. Hata durumunda sessizce None döner.
# =============================================================================

from datetime import date, timedelta
from typing import Optional, Dict, Any

import pandas as pd


FUND_CODE = "TLY"
FUND_KIND = "YAT"
HISTORY_DAYS = 50

# Uyarı eşikleri
INVESTOR_DROP_THRESHOLD = -5.0    # 7 günde %5 düşüş
AUM_DROP_THRESHOLD = -10.0        # 7 günde %10 düşüş
NAV_CONSECUTIVE_DAYS = 5          # art arda düşen gün


def _fetch_tefas_data() -> Optional[pd.DataFrame]:
    """TLY fonunun son HISTORY_DAYS günlük TEFAS verisini çeker."""
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


def _pct_change(series: pd.Series, lookback: int) -> Optional[float]:
    """Belirtilen gün kadar geriye göre % değişim. Veri yetersizse None."""
    if len(series.dropna()) < max(2, lookback):
        return None
    recent = series.dropna().iloc[-1]
    base = series.dropna().iloc[-(lookback + 1)]
    if base == 0:
        return None
    return round(((recent - base) / base) * 100.0, 2)


def _consecutive_down(series: pd.Series, n: int) -> bool:
    """Serinin son n değeri art arda azalmış mı?"""
    vals = series.dropna()
    if len(vals) < n + 1:
        return False
    window = vals.iloc[-(n + 1):]
    return all(window.iloc[i] > window.iloc[i + 1] for i in range(len(window) - 1))


def analyze_fund_health() -> Optional[Dict[str, Any]]:
    """
    TLY fonunun TEFAS verisini çeker ve uyarıları üretir.

    Returns:
        dict veya None (hata / veri yoksa):
        {
            'nav': float,                # güncel birim fiyat
            'nav_change': float,         # günlük % değişim
            'aum': float,                # portföy büyüklüğü (TL)
            'aum_change_7d': float,      # 7 günlük AUM % değişim
            'investor_count': int,       # yatırımcı sayısı
            'investor_change_7d': float, # 7 günlük yatırımcı % değişim
            'trend': str,                # 'up', 'down', 'flat'
            'warnings': list[str],       # uyarı mesajları
        }
    """
    df = _fetch_tefas_data()
    if df is None or df.empty:
        return None

    try:
        price_col = "price"
        aum_col = "portfolio_size"
        inv_col = "investor_count"

        # TEFAS bugünün verisini henüz yayınlamamışsa price=0 gelir.
        # Fiyat bazlı hesaplamalar için sadece price > 0 olan satırları kullan.
        valid_df = df[df[price_col] > 0].copy()
        if valid_df.empty:
            return None

        # NAV ve AUM: son geçerli gün
        latest_valid = valid_df.iloc[-1]
        nav = float(latest_valid[price_col])
        aum = float(latest_valid[aum_col])

        # Yatırımcı sayısı: en güncel satırdan (bugün 0-price olsa bile gelir)
        latest = df.iloc[-1]
        inv = int(latest[inv_col]) if pd.notna(latest[inv_col]) else None

        # Günlük NAV değişimi (geçerli fiyat serisinden)
        nav_series = valid_df[price_col]
        nav_change = None
        if len(nav_series) >= 2:
            n0 = nav_series.iloc[-1]
            n1 = nav_series.iloc[-2]
            if n1 != 0:
                nav_change = round(((n0 - n1) / n1) * 100.0, 2)

        # Uyarı kontrolleri
        warnings = []

        # Yatırımcı sayısı - 7 günde %5'ten fazla düşüş
        inv_change_7d = _pct_change(df[inv_col], 7)
        if inv_change_7d is not None and inv_change_7d < INVESTOR_DROP_THRESHOLD:
            warnings.append(f"⚠️ FONDAN ÇIKIŞ UYARISI: Yatırımcı sayısı 7 günde %{inv_change_7d:.1f} düştü")

        # AUM - 7 günde %10'dan fazla düşüş (geçerli seriden)
        aum_change_7d = _pct_change(valid_df[aum_col], 7)
        if aum_change_7d is not None and aum_change_7d < AUM_DROP_THRESHOLD:
            warnings.append(f"🚨 KRİTİK: FON BÜYÜKLÜĞÜ ERİYOR — 7 günde %{aum_change_7d:.1f} düştü")

        # NAV - son 5 günde art arda düşüş
        if _consecutive_down(valid_df[price_col], NAV_CONSECUTIVE_DAYS):
            warnings.append("⚠️ FON DEĞER KAYBEDİYOR: NAV son 5 günde art arda düştü")

        # 30G Trend: son 5 günlük ortalama vs önceki 5
        trend = "flat"
        trend_pct = None
        if len(valid_df) >= 10:
            recent_5 = valid_df[price_col].iloc[-5:].mean()
            prev_5 = valid_df[price_col].iloc[-10:-5].mean()
            if prev_5 > 0:
                diff = (recent_5 - prev_5) / prev_5
                trend_pct = round(diff * 100.0, 2)
                if diff > 0.002:
                    trend = "up"
                elif diff < -0.002:
                    trend = "down"

        return {
            "nav": nav,
            "nav_change": nav_change,
            "aum": aum,
            "aum_change_7d": aum_change_7d,
            "investor_count": inv,
            "investor_change_7d": inv_change_7d,
            "trend": trend,
            "trend_pct": trend_pct,
            "warnings": warnings,
        }
    except Exception:
        return None
