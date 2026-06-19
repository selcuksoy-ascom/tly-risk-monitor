# =============================================================================
# stress_test.py - Kapsamli Stres Testi & Fon Sagligi Modulu
# =============================================================================
# TEFAS tam gecmis verisi + Fonoloji holdings ile nakit tamponu, yatirimci
# kacisi, AUM erimesi, NAV trendi, konsantrasyon riski ve birlesik stres
# analizi yapar.
# Hata durumunda sessizce None doner, diger moduller etkilenmez.
# =============================================================================

from datetime import date, timedelta
from typing import Optional, Dict, Any
import urllib.request
import json

import pandas as pd
import numpy as np

FUND_CODE = "TLY"
FUND_KIND = "YAT"
HISTORY_DAYS = 90  # parametresiz cagrildiginda cekilecek gun sayisi

# Uyari esikleri
CASH_BUFFER_CRITICAL = 10.0       # %10 alti kritik
INVESTOR_DROP_WARNING = -1.0      # %1 dusus uyari
INVESTOR_DROP_CRITICAL = -3.0     # %3 dusus kritik
AUM_DROP_WARNING = -2.0           # %2 dusus uyari
AUM_DROP_CRITICAL = -5.0          # %5 dusus kritik
NAV_CONSECUTIVE_DAYS = 5
CONCENTRATION_INCREASE_WARN = 15.0  # %15 artis uyarisi
AUM_STD_MULTIPLIER = 3.0            # 3x std → buyuk tek seferlik islem


def _fetch_tefas_data(days: int = HISTORY_DAYS) -> Optional[pd.DataFrame]:
    """TLY fonunun son N gunluk TEFAS verisini ceker (parametresiz kullanim)."""
    try:
        from pytefas import Crawler
    except ImportError:
        return None

    try:
        c = Crawler()
        end = date.today()
        start = end - timedelta(days=days + 10)
        df = c.fetch(start.isoformat(), end.isoformat(), kind=FUND_KIND, fund_code=FUND_CODE)
        if df is None or df.empty:
            return None
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None


def _fetch_holdings() -> Optional[Dict[str, Any]]:
    """Fonoloji API'den TLY holdings verisini ceker. Hata sebebini debug loguna yazar."""
    try:
        from config import FONOLOJI_API_KEY
    except ImportError:
        print("  [DEBUG] config'den FONOLOJI_API_KEY import edilemedi")
        return None

    if not FONOLOJI_API_KEY:
        print("  [DEBUG] FONOLOJI_API_KEY bos — nakit tamponu hesaplanamaz")
        return None

    try:
        url = "https://fonoloji.com/v1/funds/TLY/holdings"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {FONOLOJI_API_KEY}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            print(f"  [DEBUG] Fonoloji holdings alindi, tip={type(data).__name__}")
            # Ilk birkac key'i goster
            if isinstance(data, dict):
                keys = list(data.keys())
                print(f"  [DEBUG]   root keys: {keys[:5]}")
                inner = data.get("data", data)
                if isinstance(inner, dict):
                    inner_keys = list(inner.keys())[:5]
                    print(f"  [DEBUG]   inner keys: {inner_keys}")
                    items = inner.get("holdings", inner.get("items", []))
                    if isinstance(items, list) and len(items) > 0:
                        item0 = items[0]
                        print(f"  [DEBUG]   ilk holding keys: {list(item0.keys())[:8]}")
                        print(f"  [DEBUG]   ilk holding ornek: {str(item0)[:200]}")
            return data
    except Exception as e:
        print(f"  [DEBUG] Fonoloji API hatasi: {type(e).__name__}: {e}")
        return None


def _calc_repo_ratio(holdings: Dict[str, Any]) -> Optional[float]:
    """Holdings icindeki ters repo oranini hesapla (asset_type == 'repo' weight toplami)."""
    try:
        items = holdings.get("data", holdings) if isinstance(holdings, dict) else []
        if isinstance(items, dict):
            items = items.get("holdings", items.get("items", []))
        if not isinstance(items, list):
            print(f"  [DEBUG] _calc_repo_ratio: items list degil, tip={type(items).__name__}")
            return None

        repo_weight = 0.0
        found_repo = False
        for item in items:
            if not isinstance(item, dict):
                continue
            asset_type = item.get("asset_type", item.get("type", ""))
            if isinstance(asset_type, str) and asset_type.lower() == "repo":
                weight = item.get("weight", item.get("ratio", 0))
                repo_weight += float(weight)
                found_repo = True
                print(f"  [DEBUG]   repo bulundu: weight={weight}, topRepo={repo_weight:.2f}")

        if not found_repo:
            # Varlik tiplerini listele (debug)
            types_seen = set()
            for item in items:
                if isinstance(item, dict):
                    t = item.get("asset_type", item.get("type", "?"))
                    types_seen.add(str(t))
            print(f"  [DEBUG] _calc_repo_ratio: repo bulunamadi, mevcut tipler: {sorted(types_seen)}")
            return 0.0  # repo yoksa 0 dondur (None yerine)

        return repo_weight
    except Exception as e:
        print(f"  [DEBUG] _calc_repo_ratio hata: {type(e).__name__}: {e}")
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


def _consecutive_small_aum_drops(df: pd.DataFrame, n: int = 3) -> bool:
    """
    Yatirimci sayisi sabitken AUM 3 gun ust uste %0.5-1 arasi hafif dusus var mi?
    """
    inv_col = "investor_count"
    aum_col = "portfolio_size"
    price_col = "price"

    if inv_col not in df.columns or aum_col not in df.columns or price_col not in df.columns:
        return False

    valid = df[df[price_col] > 0].copy()
    if len(valid) < n + 2:
        return False

    # Son n gunun yatirimci sayisi
    last_n_inv = df[inv_col].dropna().tail(n)
    if len(last_n_inv) < n:
        return False
    # Yatirimci sabit mi? (degisim < 1 kisi)
    if last_n_inv.max() - last_n_inv.min() > 1:
        return False

    # Son n gunde AUM her gun hafif dusuyor mu?
    aum_series = valid[aum_col].tail(n + 1)
    if len(aum_series) < n + 1:
        return False

    for i in range(1, len(aum_series)):
        prev = aum_series.iloc[i - 1]
        curr = aum_series.iloc[i]
        if prev <= 0:
            return False
        pct = (curr - prev) / prev * 100.0
        if not (-1.0 <= pct <= -0.5):
            return False

    return True


def analyze_stress_test(df_history: Optional[pd.DataFrame] = None) -> Optional[Dict[str, Any]]:
    """
    Stres testi ve fon sagligi analizi yapar.

    Args:
        df_history: Opsiyonel, money_flow.fetch_full_history() ciktisi.
                    Verilirse tam gecmis uzerinden konsantrasyon, AUM std
                    hesaplanir. Verilmezse son 90 gun cekilir.

    Returns:
        dict veya None:
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
            'nav_trend': str,
            'concentration_ratio': float,        # milyon TL/kisi
            'concentration_change_30d': float,   # % degisim
            'daily_aum_std': float,              # gunluk AUM degisim std
            'stress_level': str,
            'triggered_rule_count': int,
            'warnings': list[str],
        }
    """
    # Tam gecmis verildiyse onu kullan, yoksa kendimiz cekelim
    if df_history is not None and not df_history.empty:
        df = df_history.copy()
        df = df.sort_values("date").reset_index(drop=True)
        use_full_history = True
    else:
        df = _fetch_tefas_data()
        use_full_history = False

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

        # ---- Konsantrasyon orani (AUM / yatirimci sayisi) ----
        concentration_ratio = None
        concentration_change_30d = None
        if inv is not None and inv > 0 and aum is not None:
            concentration_ratio = round(aum / inv / 1e6, 2)  # milyon TL/kisi

            # 30 gun onceki konsantrasyon
            inv_series = df[inv_col].dropna()
            aum_valid = valid_df[aum_col].dropna()
            if len(inv_series) >= 31 and len(aum_valid) >= 31:
                inv_30d = inv_series.iloc[-31]
                aum_30d = aum_valid.iloc[-31]
                if inv_30d > 0 and aum_30d > 0:
                    conc_30d = aum_30d / inv_30d / 1e6
                    if conc_30d > 0:
                        concentration_change_30d = round(
                            ((concentration_ratio - conc_30d) / conc_30d) * 100.0, 2
                        )

        # ---- Gunluk AUM degisim standart sapmasi ----
        daily_aum_std = None
        daily_aum_change_pct = None
        if use_full_history and len(valid_df) >= 30:
            # Son 180 gunluk AUM degisimlerinin std'si
            aum_changes = valid_df[aum_col].pct_change().dropna()
            if len(aum_changes) > 0:
                daily_aum_std = round(float(aum_changes.tail(180).std()) * 100.0, 4)
                # En son gunluk AUM degisimi
                if len(aum_changes) >= 1:
                    daily_aum_change_pct = round(float(aum_changes.iloc[-1]) * 100.0, 4)

        # ---- Fonoloji holdings cek ----
        holdings = _fetch_holdings()
        repo_ratio = _calc_repo_ratio(holdings) if holdings else None

        # ---- Hesaplamalar ----
        cash_buffer = None
        coverable_exit = None
        if repo_ratio is not None and aum is not None:
            cash_buffer = (repo_ratio / 100.0) * aum if repo_ratio > 0 else 0.0
            coverable_exit = repo_ratio

        # =====================================================================
        # UYARI KURALLARI
        # =====================================================================
        warnings = []
        rule_count = 0

        # KURAL 1: Nakit tamponu yetersiz
        if coverable_exit is not None and coverable_exit < CASH_BUFFER_CRITICAL:
            warnings.append(
                f"🚨 KRİTİK: Nakit tamponu yetersiz, "
                f"yatırımcıların %{coverable_exit:.1f}'i çıkmak isterse hisse satılmak zorunda"
            )
            rule_count += 1

        # KURAL 2-3: Yatirimci degisimi
        if inv_change_7d is not None:
            if inv_change_7d < INVESTOR_DROP_CRITICAL:
                warnings.append("🚨 KRİTİK: Yatırımcı kaçışı hızlanıyor")
                rule_count += 1
            elif inv_change_7d < INVESTOR_DROP_WARNING:
                warnings.append("⚠️ UYARI: Yatırımcı sayısı azalıyor")
                rule_count += 1

        # KURAL 4-5: AUM degisimi
        if aum_change_7d is not None:
            if aum_change_7d < AUM_DROP_CRITICAL:
                warnings.append("🚨 KRİTİK: AUM hızla eriyor")
                rule_count += 1
            elif aum_change_7d < AUM_DROP_WARNING:
                warnings.append("⚠️ UYARI: AUM azalıyor")
                rule_count += 1

        # KURAL 6: NAV 5 gun art arda dusus
        if nav_down_5d:
            warnings.append("⚠️ UYARI: NAV trendi negatif, 5 gündür düşüyor")
            rule_count += 1

        # KURAL 7: Konsantrasyon orani artisi
        if concentration_change_30d is not None and concentration_change_30d > CONCENTRATION_INCREASE_WARN:
            warnings.append(
                "⚠️ UYARI: Ortalama yatırım büyüklüğü artıyor, "
                "fon büyük yatırımcılara daha bağımlı hale geliyor"
            )
            rule_count += 1

        # KURAL 8: Buyuk tek seferlik giris/cikis (gunluk AUM > 3x std)
        if daily_aum_std is not None and daily_aum_change_pct is not None and daily_aum_std > 0:
            if abs(daily_aum_change_pct) > AUM_STD_MULTIPLIER * daily_aum_std:
                direction = "giriş" if daily_aum_change_pct > 0 else "çıkış"
                warnings.append(f"👁️ Büyük tek seferlik {direction} tespit edildi")
                # Bu kural rule_count'u artirmaz, bildirim niteliginde

        # KURAL 9: Yatirimci sabit + AUM 3 gun hafif dusus → kademeli cikis
        if _consecutive_small_aum_drops(df, n=3):
            warnings.append("⚠️ Olası kademeli çıkış başlamış olabilir")
            rule_count += 1

        # KURAL 10: Birlesik stres (2+ kural aynı anda)
        if rule_count >= 2:
            warnings.append("🚨 SİSTEMİK STRES: Birden fazla risk göstergesi aynı anda alarm veriyor")

        # =====================================================================
        # STRES SEVIYESI (otomatik)
        # =====================================================================
        if rule_count >= 3:
            stress_level = "high"
        elif rule_count >= 1:
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
            "concentration_ratio": concentration_ratio,
            "concentration_change_30d": concentration_change_30d,
            "daily_aum_std": daily_aum_std,
            "stress_level": stress_level,
            "triggered_rule_count": rule_count,
            "warnings": warnings,
        }
    except Exception:
        return None
