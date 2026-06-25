# =============================================================================
# stress_test.py - Kapsamli Stres Testi & Fon Sagligi Modulu
# =============================================================================
# TEFAS tam gecmis verisi + Fonoloji public sayfa scrape ile nakit tamponu,
# yatirimci kacisi, AUM erimesi, NAV trendi, konsantrasyon riski ve birlesik
# stres analizi yapar.
# API anahtari gerektirmez, public sayfadan veri kazir.
# Hata durumunda sessizce None doner, diger moduller etkilenmez.
# =============================================================================

from datetime import date, timedelta
from typing import Optional, Dict, Any
import urllib.request
import json
import re
import sys
import time

import pandas as pd
import numpy as np

FUND_CODE = "TLY"
FUND_KIND = "YAT"
HISTORY_DAYS = 90  # parametresiz cagrildiginda cekilecek gun sayisi

# TLY fonunun tarihteki en buyuk 5 NAV dususu
# Kaynak: Fonoloji /v1/funds/TLY endpoint'i free tier'da 401 verdigi icin hardcoded
HISTORICAL_STRESS_EVENTS = [
    {"start": "2023-04-03", "end": "2023-05-16", "drawdown_pct": -32.96, "days": 43},
    {"start": "2024-05-17", "end": "2024-07-30", "drawdown_pct": -29.62, "days": 74},
    {"start": "2023-11-29", "end": "2023-12-26", "drawdown_pct": -23.46, "days": 27},
    {"start": "2025-03-18", "end": "2025-03-24", "drawdown_pct": -23.24, "days": 6},
    {"start": "2024-09-25", "end": "2024-09-30", "drawdown_pct": -22.47, "days": 5},
]

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


def _scrape_fonoloji_public() -> Dict[str, Any]:
    """Fonoloji public sayfasindan tum erisilebilir metrikleri kazir (API gerektirmez).

    Returns:
        Dict: {'cash_ratio': float|None, 'equity_ratio': float|None,
               'nav': float|None, 'aum_milyar': float|None,
               'investor_count': int|None, 'nav_change_pct': float|None,
               'aum_change_pct': float|None, 'investor_change': int|None,
               'volatility_90d': float|None, 'max_drawdown_1y': float|None,
               'sharpe_90d': float|None, 'beta_1y': float|None,
               'risk_score': str|None,  # "7/7"
               'returns': {'1m': float|None, '3m': float|None, '6m': float|None, '1y': float|None},
               'asset_allocation': {'Hisse Senedi': float|None, ...},
               'stress_events': list[dict]|None,  # public sayfadan parse edilirse
               '_source': str,  # 'next_data_json', 'regex'
              }
    """
    result = {
        "cash_ratio": None,
        "equity_ratio": None,
        "nav": None,
        "aum_milyar": None,
        "investor_count": None,
        "nav_change_pct": None,
        "aum_change_pct": None,
        "investor_change": None,
        "volatility_90d": None,
        "max_drawdown_1y": None,
        "sharpe_90d": None,
        "beta_1y": None,
        "risk_score": None,
        "returns": {"1m": None, "3m": None, "6m": None, "1y": None},
        "asset_allocation": {},
        "stress_events": None,
        "_source": "none",
    }

    try:
        url = "https://fonoloji.com/fon/TLY"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8")
    except Exception:
        return result

    # =========================================================================
    # YONTEM 1: __NEXT_DATA__ JSON blob'u (Next.js)
    # =========================================================================
    next_data = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if next_data:
        try:
            nd = json.loads(next_data.group(1))
            result["_source"] = "next_data_json"

            # Rekursif arama: tum dict/list icinde ilgili alanlari bul
            def _deep_find(obj, target_keys):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        kl = k.lower()
                        for tk in target_keys:
                            if tk in kl:
                                return v
                        r = _deep_find(v, target_keys)
                        if r is not None:
                            return r
                elif isinstance(obj, list):
                    for item in obj:
                        r = _deep_find(item, target_keys)
                        if r is not None:
                            return r
                return None

            def _deep_find_dict(obj, key_hint):
                """key_hint iceren dict'i bul (varlik dagilimi gibi)."""
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if key_hint in k.lower() and isinstance(v, (dict, list)):
                            return v
                        r = _deep_find_dict(v, key_hint)
                        if r is not None:
                            return r
                elif isinstance(obj, list):
                    for item in obj:
                        r = _deep_find_dict(item, key_hint)
                        if r is not None:
                            return r
                return None

            # NAV
            nav_val = _deep_find(nd, ["nav", "price", "birimpay"])
            if nav_val is not None:
                try:
                    result["nav"] = float(nav_val)
                except (ValueError, TypeError):
                    pass

            # AUM
            aum_val = _deep_find(nd, ["aum", "fundsize", "portfoliosize", "fonbuyuklugu"])
            if aum_val is not None:
                try:
                    result["aum_milyar"] = float(aum_val) / 1e9
                except (ValueError, TypeError):
                    pass

            # Yatirimci
            inv_val = _deep_find(nd, ["investor", "yatirimci", "participant"])
            if inv_val is not None:
                try:
                    result["investor_count"] = int(float(inv_val))
                except (ValueError, TypeError):
                    pass

            # Composition / asset allocation
            comp = _deep_find_dict(nd, "compos")
            if comp is None:
                comp = _deep_find_dict(nd, "asset")
            if comp is None:
                comp = _deep_find_dict(nd, "allocation")
            if isinstance(comp, list):
                alloc = {}
                for item in comp:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("label") or item.get("type") or item.get("asset_type") or ""
                        ratio = item.get("ratio") or item.get("percentage") or item.get("value") or item.get("weight") or 0
                        if name and ratio:
                            try:
                                alloc[str(name)] = float(ratio)
                            except (ValueError, TypeError):
                                pass
                if alloc:
                    result["asset_allocation"] = alloc
                    for k, v in alloc.items():
                        kl = k.lower()
                        if "nakit" in kl or "mevduat" in kl or "cash" in kl:
                            if result["cash_ratio"] is None:
                                result["cash_ratio"] = v
                        if "hisse" in kl or "equity" in kl or "stock" in kl:
                            if result["equity_ratio"] is None:
                                result["equity_ratio"] = v

            # Sharpe, volatility, drawdown
            sharpe = _deep_find(nd, ["sharpe"])
            if sharpe is not None:
                try:
                    result["sharpe_90d"] = float(sharpe)
                except (ValueError, TypeError):
                    pass
            vol = _deep_find(nd, ["volatil", "volatility"])
            if vol is not None:
                try:
                    result["volatility_90d"] = float(vol)
                except (ValueError, TypeError):
                    pass
            dd = _deep_find(nd, ["drawdown", "maxdd", "max_dd"])
            if dd is not None:
                try:
                    v = float(str(dd).replace("%", "").replace("-", ""))
                    result["max_drawdown_1y"] = v
                except (ValueError, TypeError):
                    pass

            # Returns
            for label, key in [("1m", "1ay"), ("3m", "3ay"), ("6m", "6ay"), ("1y", "1yil")]:
                rv = _deep_find(nd, [key, label])
                if rv is not None:
                    try:
                        result["returns"][label] = float(str(rv).replace("%", ""))
                    except (ValueError, TypeError):
                        pass

        except Exception:
            result["_source"] = "next_data_parse_error"

    # =========================================================================
    # YONTEM 2: Regex fallback (__NEXT_DATA__ yoksa veya parse basarisizsa)
    # =========================================================================
    if result["_source"] in ("none", "next_data_parse_error"):
        result["_source"] = "regex"

        def _try_float(pattern, text, group=1):
            m = re.search(pattern, text)
            if m:
                try:
                    return float(m.group(group).replace(",", ".").replace(" ", ""))
                except ValueError:
                    pass
            return None

        def _try_int(pattern, text, group=1):
            m = re.search(pattern, text)
            if m:
                try:
                    return int(m.group(group).replace(",", "").replace(".", "").replace(" ", ""))
                except ValueError:
                    pass
            return None

        # NAV fiyati — sayfada birden fazla yerde gecen fiyat degerlerinden
        # en guvenilirini al: 6.567,XX formatinda 4+ haneli
        for nav_pat in [
            r'>\s*(\d{1,3}(?:\.\d{3})*(?:,\d+))\s*<',  # formatted price
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{4,}))',       # NAV with many decimals
        ]:
            nav_val = _try_float(nav_pat, html)
            if nav_val and nav_val > 100:  # NAV > 100 TL
                result["nav"] = nav_val
                break

        # Gunluk NAV degisimi
        result["nav_change_pct"] = _try_float(r'(?:günlük|bugün|değişim).*?([+-]?\d+[.,]\d+)\s*%', html)

        # AUM: Fonoloji sayfasinda "X milyar TL" veya "fon büyüklüğü"
        aum = _try_float(r'(?:fon\s*büyüklüğü|AUM)[^0-9]*([\d.,]+)\s*milyar', html)
        if aum is None:
            aum = _try_float(r'([\d.,]+)\s*milyar\s*(?:TL|₺)', html)
        result["aum_milyar"] = aum

        # Yatirimci sayisi
        result["investor_count"] = _try_int(r'(?:Yatırımcı|Yatirimci)[^0-9]*?(\d{1,3}(?:\.\d{3})*(?:,\d+)?)', html)

        # ===== VARLIK DAGILIMI: progress bar width uzerinden kazir =====
        # Allocation bolumunde her varlik sinifi icin bir progress bar var:
        # <span class="truncate">Nakit / Mevduat</span> ...
        # <span style="width:15.64%"></span>
        # Bu yapi sadece varlik dagiliminda var, gunluk degisim bolumunde yok.
        alloc = {}
        for m in re.finditer(
            r'<span\s+class="truncate">([^<]+)</span>'
            r'.*?'
            r'style="width:\s*(\d+[.,]\d+)%\s*;[^"]*"',
            html, re.DOTALL,
        ):
            name = m.group(1).strip()
            try:
                val = float(m.group(2).replace(',', '.'))
                alloc[name] = val
                if result["cash_ratio"] is None and ('nakit' in name.lower() or 'mevduat' in name.lower()):
                    result["cash_ratio"] = val
                if result["equity_ratio"] is None and 'hisse' in name.lower():
                    result["equity_ratio"] = val
            except (ValueError, IndexError):
                pass
        if alloc:
            result["asset_allocation"] = alloc

        # Fallback: orijinal regex yaklasimi (progress bar bulunamazsa)
        if not alloc:
            KNOWN_CLASSES = [
                (r'Hisse\s*Senedi', 'Hisse Senedi'),
                (r'Devlet\s*(?:Tahvili|İç\s*Borçlanma)', 'Devlet Tahvili'),
                (r'Özel\s*Sektör', 'Ozel Sektor'),
                (r'Nakit\s*/\s*Mevduat', 'Nakit / Mevduat'),
                (r'Nakit', 'Nakit / Mevduat'),
                (r'Mevduat', 'Nakit / Mevduat'),
                (r'Diğer', 'Diger'),
            ]
            for pat, label in KNOWN_CLASSES:
                m = re.search(pat + r'[^%]*%(?:<!--[^>]*-->)?\s*(\d+[.,]\d+)', html)
                if m:
                    try:
                        val = float(m.group(1).replace(',', '.'))
                        alloc[label] = val
                        if label == 'Nakit / Mevduat' and result["cash_ratio"] is None:
                            result["cash_ratio"] = val
                        if label == 'Hisse Senedi' and result["equity_ratio"] is None:
                            result["equity_ratio"] = val
                    except (ValueError, IndexError):
                        pass
            if alloc:
                result["asset_allocation"] = alloc

            # Daha genis fallback
            if not alloc:
                for m in re.finditer(r'(Hisse\s*Senedi|Nakit[^%]*|Mevduat[^%]*|Özel\s*Sektör|Devlet\s*Tahvili|Diğer)[^%]*%(?:<!--[^>]*-->)?\s*(\d+[.,]\d+)', html):
                    name = m.group(1).strip()
                    try:
                        val = float(m.group(2).replace(',', '.'))
                        alloc[name] = val
                    except (ValueError, IndexError):
                        pass
                if alloc:
                    result["asset_allocation"] = alloc
                    if result["cash_ratio"] is None:
                        for k, v in alloc.items():
                            if 'nakit' in k.lower() or 'mevduat' in k.lower():
                                result["cash_ratio"] = v
                                break
                    if result["equity_ratio"] is None:
                        for k, v in alloc.items():
                            if 'hisse' in k.lower():
                                result["equity_ratio"] = v
                                break

        # Sharpe
        result["sharpe_90d"] = _try_float(r'[Ss]harpe[^0-9]*(\d+[.,]\d+)', html)
        # Volatilite
        result["volatility_90d"] = _try_float(r'[Vv]olatilite[^0-9]*%?(\d+[.,]\d+)', html)
        # Max drawdown
        dd = _try_float(r'[Mm]ax\s*[Dd]rawdown[^0-9]*%?(\d+[.,]\d+)', html)
        if dd:
            result["max_drawdown_1y"] = dd
        # Beta
        result["beta_1y"] = _try_float(r'[Bb]eta[^0-9]*(\d+[.,]\d+)', html)
        # Risk skoru
        rsm = re.search(r'[Rr]isk\s*(?:[Dd]eğeri|Skoru|Seviyesi)[^0-9]*(\d+\s*/\s*\d+)', html)
        if rsm:
            result["risk_score"] = rsm.group(1).replace(' ', '')

    return result


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


def get_historical_stress_comparison(stress_level: str, nav_trend: str) -> str:
    """Mevcut stres seviyesini tarihsel en kotu 5 NAV dususuyle karsilastirir.

    Args:
        stress_level: "high", "medium", veya "low"
        nav_trend: "up", "down", veya "flat"

    Returns:
        Tarihsel karsilastirma metni (Turkce).
    """
    lines = []
    event_lines = []
    for i, ev in enumerate(HISTORICAL_STRESS_EVENTS, 1):
        event_lines.append(
            f"  {i}. {ev['start']} -> {ev['end']}: %{ev['drawdown_pct']:.2f} ({ev['days']} gun)"
        )
    events_text = "\n".join(event_lines)

    if stress_level == "high" and nav_trend == "down":
        worst = HISTORICAL_STRESS_EVENTS[0]
        lines.append(
            f"Mevcut yuksek stres ve dusen NAV trendi, tarihteki en kotu "
            f"5 NAV cokusuyle karsilastirilabilir duzeyde. "
            f"En sert dusus %{abs(worst['drawdown_pct']):.1f} ile "
            f"{worst['start']} - {worst['end']} arasinda ({worst['days']} gun) gerceklesmisti."
        )
        lines.append(events_text)
    elif stress_level == "high":
        lines.append(
            f"Stres seviyesi yuksek ancak NAV trendi henuz belirgin bir dusus "
            f"gostermiyor. Tarihteki en kotu 5 NAV cokusu asagidadir. "
            f"Mevcut durum henuz bu seviyelerde degil."
        )
        lines.append(events_text)
    elif stress_level == "medium":
        lines.append(
            f"Stres seviyesi orta duzeyde. Tarihte cok daha sert donemler goruldu. "
            f"Ornegin en sert dusus %{abs(HISTORICAL_STRESS_EVENTS[0]['drawdown_pct']):.1f} "
            f"({HISTORICAL_STRESS_EVENTS[0]['start']} - {HISTORICAL_STRESS_EVENTS[0]['end']}). "
            f"Su anki durum kontrol altinda."
        )
    else:
        lines.append(
            f"Dusuk stres seviyesi. Tarihsel NAV cokusleriyle karsilastirildiginda "
            f"fon su an sakin bir donemden geciyor. En sert 5 tarihsel dusus:"
        )
        lines.append(events_text)

    return "\n".join(lines)


def analyze_stress_test(
    df_history: Optional[pd.DataFrame] = None,
    holdings: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Stres testi ve fon sagligi analizi yapar.

    Args:
        df_history: Opsiyonel, money_flow.fetch_full_history() ciktisi.
                    Verilirse tam gecmis uzerinden konsantrasyon, AUM std
                    hesaplanir. Verilmezse son 90 gun cekilir.
        holdings: Kullanilmiyor (geriye uyumluluk). Nakit orani Fonoloji
                  public sayfasindan kazimir.

    Returns:
        dict veya None. Detayli alanlar icin kod icinde return dict'e bakiniz.
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
        nav_trend_pct = None
        if len(valid_df) >= 10:
            recent_5 = valid_df[price_col].iloc[-5:].mean()
            prev_5 = valid_df[price_col].iloc[-10:-5].mean()
            if prev_5 > 0:
                diff = (recent_5 - prev_5) / prev_5
                nav_trend_pct = round(diff * 100.0, 2)
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

        # ---- Nakit tamponu: Fonoloji public sayfasindan kazir ----
        fonoloji_error = None
        repo_ratio = None
        scraped = _scrape_fonoloji_public()
        repo_ratio = scraped.get("cash_ratio")
        if repo_ratio is None:
            src = scraped.get("_source", "?")
            alloc = scraped.get("asset_allocation", {})
            fonoloji_error = f"Public sayfada nakit/mevduat orani bulunamadi (source={src}, alloc_keys={list(alloc.keys())[:5]})"

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

        historical_stress_comparison = get_historical_stress_comparison(stress_level, nav_trend)

        return {
            "nav": nav,
            "nav_change": nav_change,
            "aum": aum,
            "aum_change_7d": aum_change_7d,
            "investor_count": inv,
            "investor_change_7d": inv_change_7d,
            "_fonoloji_error": fonoloji_error,
            "repo_ratio": repo_ratio,
            "cash_buffer": cash_buffer,
            "coverable_exit": coverable_exit,
            "nav_down_5d": nav_down_5d,
            "nav_trend": nav_trend,
            "nav_trend_pct": nav_trend_pct,
            "concentration_ratio": concentration_ratio,
            "concentration_change_30d": concentration_change_30d,
            "daily_aum_std": daily_aum_std,
            "stress_level": stress_level,
            "triggered_rule_count": rule_count,
            "warnings": warnings,
            "historical_stress_comparison": historical_stress_comparison,
            "_fonoloji_public": scraped,  # public sayfadan kazinan tum veriler
        }
    except Exception:
        return None
