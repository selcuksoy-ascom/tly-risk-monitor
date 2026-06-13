# =============================================================================
# risk_analyzer.py - Risk Analiz Motoru
# =============================================================================
# 3 temel kural ile yanlış sinyal üretimini engeller:
#   KURAL 1 - Likidite Kilitlenmesi
#   KURAL 2 - Başarılı Çıkış (False Positive Filtresi)
#   KURAL 3 - Sistemik Çöküş Radarı
# =============================================================================

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from config import (
    WEIGHT_THRESHOLD,
    PRICE_DROP_THRESHOLD,
    VOLUME_LOCKDOWN_THRESHOLD,
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
# Ana Analiz Fonksiyonu
# ---------------------------------------------------------------------------

def analyze_portfolio(
    portfolio_data: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Tüm portföyü analiz eder, her hisse için risk durumunu döndürür.

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

    for ticker, data in portfolio_data.items():
        if data.get("error"):
            per_stock[ticker] = {
                **data,
                "liquidity_status": "VERİ YOK",
                "volume_ratio": None,
                "is_critical": False,
                "is_rotation": False,
                "alert_message": None,
            }
            continue

        weight = data["weight"]
        change_pct = data["change_pct"]
        volume = data["volume"]
        avg_volume = data["avg_volume"]
        prev_weight = data.get("prev_weight", weight)

        # ----- KURAL 2 önce çalışır (false positive filtresi) -----
        is_rotation, rotation_msg = check_rotation_exit(
            ticker, change_pct, volume, avg_volume, weight, prev_weight
        )

        if is_rotation:
            rotation_logs.append(f"{ticker}: {rotation_msg}")
            per_stock[ticker] = {
                **data,
                "liquidity_status": "ROTASYON",
                "volume_ratio": (volume / avg_volume * 100) if avg_volume else None,
                "is_critical": False,
                "is_rotation": True,
                "alert_message": rotation_msg,
            }
            continue

        # ----- KURAL 1: Likidite Kilitlenmesi -----
        is_critical, liq_msg, vol_ratio = check_liquidity_lockdown(
            ticker, weight, change_pct, volume, avg_volume
        )

        if is_critical:
            alert = f"{ticker} ({data['name']}): {liq_msg}"
            critical_alerts.append(alert)

        per_stock[ticker] = {
            **data,
            "liquidity_status": liq_msg,
            "volume_ratio": round(vol_ratio, 1),
            "is_critical": is_critical,
            "is_rotation": False,
            "alert_message": liq_msg if is_critical else None,
        }

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

    return {
        "per_stock": per_stock,
        "systemic": systemic_result,
        "critical_alerts": critical_alerts,
        "rotation_logs": rotation_logs,
    }
