# =============================================================================
# risk_analyzer.py - Risk Analiz Motoru
# =============================================================================
# 4 temel kural ile yanlış sinyal üretimini engeller:
#   KURAL 1 - Likidite Kilitlenmesi
#   KURAL 2 - Başarılı Çıkış (False Positive Filtresi)
#   KURAL 3 - Sistemik Çöküş Radarı
#   KURAL 4 - Sığ Piyasa Uyarısı
# =============================================================================

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from config import (
    WEIGHT_THRESHOLD,
    PRICE_DROP_THRESHOLD,
    VOLUME_LOCKDOWN_THRESHOLD,
    VOLUME_THIN_MARKET_THRESHOLD,
    CORRELATION_THRESHOLD,
    GROUP_TICKERS,
)


# ---------------------------------------------------------------------------
# KURAL 1: Likidite Kilitlenmesi
# ---------------------------------------------------------------------------

def check_liquidity_lockdown(
    ticker: str,
    weight: float,
    change_pct: float,
    volume: int,
    avg_volume: Optional[float],
) -> Tuple[bool, str, float]:
    """
    KOŞUL A: Likidite kilitlenmesi tespiti.

    Tetikleyici:
      - Ağırlık > %10  (büyük pozisyon)
      - Fiyat değişimi < -%5  (sert düşüş)
      - Hacim < 30 günlük ortalamanın %50'si  (likidite kuruması)

    Returns:
        (is_critical, message, volume_ratio)
    """
    # Veri eksikse değerlendirme yapılamaz
    if change_pct is None or volume is None or avg_volume is None:
        return False, "VERİ YOK", 0.0

    # Hacim oranını hesapla
    if avg_volume and avg_volume > 0:
        volume_ratio = (volume / avg_volume) * 100.0
    else:
        volume_ratio = 100.0  # Referans yok, normal kabul et

    # Üç koşul birden sağlanmalı
    condition_weight = weight > WEIGHT_THRESHOLD
    condition_drop = change_pct < PRICE_DROP_THRESHOLD
    condition_volume = (volume_ratio / 100.0) < VOLUME_LOCKDOWN_THRESHOLD

    if condition_weight and condition_drop and condition_volume:
        msg = "KRİTİK: LİKİDİTE KİLİTLENMESİ"
        return True, msg, volume_ratio

    return False, "Normal", volume_ratio


# ---------------------------------------------------------------------------
# KURAL 2: Başarılı Çıkış (False Positive Filtresi)
# ---------------------------------------------------------------------------

def check_rotation_exit(
    ticker: str,
    change_pct: float,
    volume: int,
    avg_volume: Optional[float],
    current_weight: float,
    prev_weight: float,
) -> Tuple[bool, str]:
    """
    KOŞUL B: Fon aktif olarak pozisyon azaltıyorsa, düşüşü alarm olarak sayma.

    Tetikleyici (alarm VERİLMEZ):
      - Fiyat düşüyor  (change_pct < 0)
      - Hacim yüksek   (volume > ortalama)
      - Ağırlık önceki aydan azalmış  (başarılı çıkış kanıtı)

    Returns:
        (is_rotation, message)
    """
    if change_pct is None or volume is None:
        return False, ""

    if avg_volume and avg_volume > 0:
        volume_ratio = volume / avg_volume
    else:
        volume_ratio = 1.0

    is_falling = change_pct < 0
    is_high_volume = volume_ratio > 1.0
    is_weight_reduced = current_weight < prev_weight

    if is_falling and is_high_volume and is_weight_reduced:
        return True, "ROTASYON: Başarılı Çıkış (False Positive Filtre aktif)"

    return False, ""


# ---------------------------------------------------------------------------
# KURAL 3: Sistemik Çöküş Radarı
# ---------------------------------------------------------------------------

def check_systemic_collapse(
    portfolio_data: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[float], bool, str]:
    """
    TERA grubu hisseleri (TERA.IS, TRHOL.IS, TEHOL.IS) arasındaki
    30 günlük fiyat korelasyonunu hesaplar.

    Tetikleyici:
      - Korelasyon > 0.80  (yüksek senkronizasyon)
      - Üçü de aynı gün negatif kapanıyor

    Returns:
        (correlation_mean, is_critical, message)
    """
    # Grup hisselerinin geçmiş verilerini topla
    price_series = {}
    available_tickers = []

    for ticker in GROUP_TICKERS:
        if ticker not in portfolio_data:
            continue
        data = portfolio_data[ticker]
        if data.get("history") is not None and not data["history"].empty:
            price_series[ticker] = data["history"]["Close"]
            available_tickers.append(ticker)

    if len(available_tickers) < 2:
        return None, False, "Yeterli grup verisi yok"

    # DataFrame oluştur ve hizala
    prices_df = pd.DataFrame(price_series)
    prices_df = prices_df.dropna()

    if len(prices_df) < 5:
        return None, False, "Yetersiz geçmiş veri"

    # Korelasyon matrisi
    corr_matrix = prices_df.corr()

    # Ortalama off-diagonal korelasyon
    n = len(corr_matrix)
    if n < 2:
        return None, False, "Tek hisse"

    corr_values = []
    for i in range(n):
        for j in range(i + 1, n):
            corr_values.append(corr_matrix.iloc[i, j])

    mean_corr = float(np.mean(corr_values))

    # Bugün üçü de negatif mi?
    all_negative_today = all(
        portfolio_data.get(t, {}).get("change_pct", 0) is not None
        and portfolio_data.get(t, {}).get("change_pct", 0) < 0
        for t in available_tickers
    )

    is_critical = (mean_corr > CORRELATION_THRESHOLD) and all_negative_today

    if is_critical:
        msg = "KRİTİK: DÖNGÜSEL SERMAYE YAPISINDA BOZULMA"
    elif mean_corr > CORRELATION_THRESHOLD:
        msg = f"UYARI: Yüksek korelasyon (hepsi aynı anda negatif değil)"
    else:
        msg = "Normal"

    return round(mean_corr, 4), is_critical, msg


# ---------------------------------------------------------------------------
# KURAL 4: Sığ Piyasa Uyarısı
# ---------------------------------------------------------------------------

def check_thin_market(
    ticker: str,
    weight: float,
    volume: int,
    avg_volume: Optional[float],
) -> Tuple[bool, str]:
    """
    KOŞUL D: Sığ piyasa — fiyat yönünden bağımsız likidite uyarısı.

    Tetikleyici:
      - Ağırlık > %10  (büyük pozisyon)
      - Hacim < 30 günlük ortalamanın %20'si

    Fiyat yükseliyor olsa bile tetiklenir. Amaç: pozisyon büyükken
    piyasanın sığ olduğunu, çıkışta zorlanılacağını erkenden bildirmek.

    Returns:
        (is_thin, message)
    """
    if volume is None or avg_volume is None or avg_volume <= 0:
        return False, ""

    is_large_position = weight > WEIGHT_THRESHOLD

    # Hacim oranı
    volume_ratio = volume / avg_volume

    is_thin_volume = volume_ratio < VOLUME_THIN_MARKET_THRESHOLD

    if is_large_position and is_thin_volume:
        return True, "SIĞ PİYASA: Büyük pozisyon, çok düşük hacimli piyasa"

    return False, ""


# ---------------------------------------------------------------------------
# KURAL 5: Taban Serisi Tespiti
# ---------------------------------------------------------------------------

LIMIT_DOWN_THRESHOLD = -9.5          # BIST taban: -%10 (tolerans ile -%9.5)
LIMIT_DOWN_TODAY_WARN = -5.0         # Bugun -5% alti + dun tabansa → erken uyari

def check_floor_series(
    ticker: str,
    change_pct: Optional[float],
    history: Optional[pd.DataFrame],
) -> Tuple[bool, str, bool]:
    """
    KURAL 5: Art arda taban yapan hisseyi tespit eder.

    Tetikleyici:
      - Bugun taban (-%9.5 veya alti) VE dun de tabandi  → 🚨 KRITIK TABAN SERISI
      - Bugun taban (tek basina)                          → ⚠️  TABAN UYARISI (yarin tekrar ederse kritik)

    Returns:
        (is_critical, is_warning, message) — critical doubles as warning
    """
    if change_pct is None:
        return False, False, ""

    today_is_floor = change_pct <= LIMIT_DOWN_THRESHOLD

    if not today_is_floor:
        return False, False, ""

    # Bugun taban — tek gunluk uyari her zaman verilir
    single_msg = (
        f"⚠️ TABAN: {ticker} bugun %{change_pct:.1f} ile taban yapti, "
        f"yarin tekrar taban olursa kritik alarm tetiklenir"
    )

    if history is None or history.empty or len(history) < 3:
        return False, True, single_msg

    try:
        close_prices = history["Close"]
        if len(close_prices) < 3:
            return False, True, single_msg

        yesterday_close = float(close_prices.iloc[-2])
        prev_day_close = float(close_prices.iloc[-3])

        if prev_day_close > 0 and yesterday_close > 0:
            yesterday_change = ((yesterday_close - prev_day_close) / prev_day_close) * 100.0
        else:
            return False, True, single_msg

        yesterday_was_floor = yesterday_change <= LIMIT_DOWN_THRESHOLD

        if yesterday_was_floor:
            return True, True, (
                f"🚨 TABAN SERISI: {ticker} art arda 2 gun taban "
                f"(dun %{yesterday_change:.1f}, bugun %{change_pct:.1f})"
            )
        else:
            return False, True, single_msg

    except Exception:
        pass

    return False, True, single_msg


# ---------------------------------------------------------------------------
# Ana Analiz Fonksiyonu
# ---------------------------------------------------------------------------

def analyze_portfolio(
    portfolio_data: Dict[str, Dict[str, Any]],
    fund_health: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Tüm portföyü analiz eder, her hisse için risk durumunu döndürür.

    Args:
        portfolio_data: fetch_all_portfolio_data() ciktisi
        fund_health: Opsiyonel, tefas_fetcher.analyze_fund_health() ciktisi.
                     Sessiz cokus tespiti icin kullanilir.

    Returns:
        {
            'per_stock': {ticker: {...risk_info...}},
            'systemic': {...},
            'critical_alerts': [...],
            'rotation_logs': [...],
        }
    """
    per_stock = {}
    critical_alerts = []
    rotation_logs = []
    thin_market_alerts = []

    for ticker, data in portfolio_data.items():
        if data.get("error"):
            per_stock[ticker] = {
                **data,
                "liquidity_status": "VERİ YOK",
                "volume_ratio": None,
                "is_critical": False,
                "is_rotation": False,
                "is_thin_market": False,
                "is_fund": False,
                "alert_message": None,
            }
            continue

        # Fon/GYF tipi varlıklar — likidite analizi yapılmaz
        if data.get("is_fund"):
            per_stock[ticker] = {
                **data,
                "liquidity_status": "FON - İzleme Dışı",
                "volume_ratio": None,
                "is_critical": False,
                "is_rotation": False,
                "is_thin_market": False,
                "is_fund": True,
                "alert_message": None,
            }
            continue

        weight = float(data["weight"])
        change_pct = float(data["change_pct"]) if data["change_pct"] is not None else None
        volume = int(data["volume"]) if data["volume"] is not None else None
        avg_volume = float(data["avg_volume"]) if data["avg_volume"] is not None else None
        prev_weight = float(data.get("prev_weight", weight))

        # Hacim oranı (tüm kurallarda kullanılacak)
        if avg_volume and avg_volume > 0:
            vol_ratio = (volume / avg_volume) * 100.0
        else:
            vol_ratio = 100.0

        # ----- KURAL 2 önce çalışır (false positive filtresi) -----
        is_rotation, rotation_msg = check_rotation_exit(
            ticker, change_pct, volume, avg_volume, weight, prev_weight
        )

        if is_rotation:
            rotation_logs.append(f"{ticker}: {rotation_msg}")
            per_stock[ticker] = {
                **data,
                "liquidity_status": "ROTASYON",
                "volume_ratio": round(vol_ratio, 1),
                "is_critical": False,
                "is_rotation": True,
                "is_thin_market": False,
                "alert_message": rotation_msg,
            }
            continue

        # ----- KURAL 4: Sığ Piyasa Uyarısı (fiyat yönünden bağımsız) -----
        is_thin, thin_msg = check_thin_market(
            ticker, weight, volume, avg_volume
        )

        if is_thin:
            thin_market_alerts.append(f"{ticker} ({data['name']}): {thin_msg}")

        # ----- KURAL 1: Likidite Kilitlenmesi -----
        is_critical, liq_msg, _ = check_liquidity_lockdown(
            ticker, weight, change_pct, volume, avg_volume
        )

        if is_critical:
            alert = f"{ticker} ({data['name']}): {liq_msg}"
            critical_alerts.append(alert)

        # Durum mesajını belirle (kritik > sığ piyasa > normal)
        if is_critical:
            status_msg = liq_msg
        elif is_thin:
            status_msg = thin_msg
        else:
            status_msg = "Normal"

        per_stock[ticker] = {
            **data,
            "liquidity_status": status_msg,
            "volume_ratio": round(vol_ratio, 1),
            "is_critical": is_critical,
            "is_rotation": False,
            "is_thin_market": is_thin,
            "alert_message": liq_msg if is_critical else (thin_msg if is_thin else None),
        }

        # ----- KURAL 5: Taban Serisi Kontrolü (her hisse icin) -----
        is_floor_crit, is_floor_warn, floor_msg = check_floor_series(
            ticker, change_pct, data.get("history")
        )

        if is_floor_crit:
            critical_alerts.append(f"{ticker} ({data['name']}): {floor_msg}")
            per_stock[ticker]["is_critical"] = True
            existing_alert = per_stock[ticker].get("alert_message")
            if existing_alert:
                per_stock[ticker]["alert_message"] = f"{existing_alert} | {floor_msg}"
            else:
                per_stock[ticker]["alert_message"] = floor_msg
        elif is_floor_warn:
            thin_market_alerts.append(f"{ticker} ({data['name']}): {floor_msg}")

    # ----- KURAL 3: Sistemik Çöküş -----
    corr_value, is_systemic, systemic_msg = check_systemic_collapse(portfolio_data)

    if is_systemic:
        critical_alerts.append(f"GRUP HİSSELERİ: {systemic_msg}")

    systemic_result = {
        "correlation": corr_value,
        "is_critical": is_systemic,
        "message": systemic_msg,
        "tickers": GROUP_TICKERS,
    }

    # ----- KOMBINASYON KURALI A: CIFT LIKIDITE KILIDI -----
    ozatd = per_stock.get("OZATD.IS", {})
    dstkf = per_stock.get("DSTKF.IS", {})
    if not ozatd.get("is_fund") and not dstkf.get("is_fund"):
        try:
            ozatd_vol = float(ozatd.get("volume_ratio")) if ozatd.get("volume_ratio") is not None else None
            dstkf_vol = float(dstkf.get("volume_ratio")) if dstkf.get("volume_ratio") is not None else None
            if ozatd_vol is not None and dstkf_vol is not None:
                if ozatd_vol < 20.0 and dstkf_vol < 50.0:
                    alert = "🚨 ÇİFT LİKİDİTE KİLİDİ: OZATD ve DSTKF eşzamanlı hacim düşüşü"
                    critical_alerts.append(alert)
        except (ValueError, TypeError):
            pass

    # ----- KOMBINASYON KURALI B: GRUP SARMALI -----
    # TERA+TRHOL+TEHOL ucu de -%3 altinda VE korelasyon > 0.80
    group_all_below_3 = True
    for t in GROUP_TICKERS:
        chg = per_stock.get(t, {}).get("change_pct")
        try:
            chg = float(chg) if chg is not None else None
        except (ValueError, TypeError):
            chg = None
        if chg is None or chg >= -3.0:
            group_all_below_3 = False
            break

    corr_value = systemic_result.get("correlation")
    if group_all_below_3 and corr_value is not None and corr_value > CORRELATION_THRESHOLD:
        alert = "🚨 GRUP SARMALI BAŞLADI: TERA, TRHOL, TEHOL eşzamanlı sert düşüş + yüksek korelasyon"
        if alert not in critical_alerts:
            critical_alerts.append(alert)

    # ----- KOMBINASYON KURALI C: SESSIZ COKUS -----
    # NAV 3 gun art arda dustu VE yatirimci azaliyor VE hisse hacimleri normal
    if fund_health is not None and isinstance(fund_health, dict):
        nav_down = False
        fh_warnings = fund_health.get("warnings", [])
        if isinstance(fh_warnings, list):
            for w in fh_warnings:
                if isinstance(w, str) and ("art arda" in w.lower() or "değer kaybediyor" in w.lower()):
                    nav_down = True
                    break
        # Alternatif: NAV trend asagi ve son 5 gun dustu uyarisi varsa
        if not nav_down:
            fh_trend = fund_health.get("trend", "")
            if isinstance(fh_trend, str) and fh_trend == "down":
                nav_down = True

        inv_decreasing = False
        inv_change = fund_health.get("investor_change_7d")
        if inv_change is not None:
            try:
                inv_change = float(inv_change)
                if inv_change < 0:
                    inv_decreasing = True
            except (ValueError, TypeError):
                pass

        # Hisse hacimleri normal mi? (kritik veya sig piyasa yok)
        volumes_normal = (
            len(critical_alerts) == 0 and
            len(thin_market_alerts) == 0
        )

        if nav_down and inv_decreasing and volumes_normal:
            thin_market_alerts.append(
                "⚠️ SESSİZ ÇÖKÜŞ: Görünürde alarm yok ama fon değer kaybediyor"
            )

    return {
        "per_stock": per_stock,
        "systemic": systemic_result,
        "critical_alerts": critical_alerts,
        "rotation_logs": rotation_logs,
        "thin_market_alerts": thin_market_alerts,
    }
