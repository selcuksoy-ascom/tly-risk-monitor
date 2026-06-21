# =============================================================================
# summary_generator.py - Gunluk Ozet ve Otomatik Yorum Uretici
# =============================================================================
# Tum risk modullerinden gelen verileri birlestirerek kural tabanli,
# oncelik sirali, tek paragraf Turkce gunluk ozet metni uretir.
# AI/LLM kullanmaz, tamamen if/else mantigiyla calisir.
# =============================================================================

from typing import Dict, Any, Optional


def _calc_net_portfolio_effect(per_stock: Dict[str, Dict[str, Any]]) -> float:
    """Hisse agirliklari ve gunluk degisimlerden net portfoy etkisini hesapla."""
    total = 0.0
    count = 0
    for data in per_stock.values():
        w = data.get("weight", 0)
        chg = data.get("change_pct") or 0
        total += w * chg
        count += 1
    if count == 0:
        return 0.0
    return round(total / 100.0, 2)


def generate_daily_summary(
    stress: Optional[Dict[str, Any]],
    analysis: Dict[str, Any],
    fund_health: Optional[Dict[str, Any]],
    rotation: Optional[Dict[str, Any]],
    sim: Optional[Dict[str, Any]],
) -> str:
    """Tum modullerden gelen verileri birlestirerek gunluk ozet metni uretir.

    Oncelik sirasi:
      1. Kritik alarmlar, taban serisi, sistemik spiral, yuksek stres, net etki < -%3
      2. Orta stres, havuz daralmasi, konsantrasyon artisi, NAV 5g dusus
      3. Sakin gun, hicbir sey tetiklenmemis

    Args:
        stress: stress_test.analyze_stress_test() ciktisi veya None
        analysis: risk_analyzer.analyze_portfolio() ciktisi
        fund_health: tefas_fetcher.analyze_fund_health() ciktisi veya None
        rotation: rotation_tracker.analyze_rotation() ciktisi veya None
        sim: simulator.run_simulation() ciktisi veya None

    Returns:
        Formatlanmis Turkce ozet paragrafi.
    """
    lines = []

    # --- Yardimci veri cekimleri ---
    critical_alerts = analysis.get("critical_alerts", [])
    stress_level = stress.get("stress_level", "low") if stress else "low"
    triggered = stress.get("triggered_rule_count", 0) if stress else 0
    nav_trend = stress.get("nav_trend", "flat") if stress else "flat"
    per_stock = analysis.get("per_stock", {})
    net_effect = _calc_net_portfolio_effect(per_stock)
    systemic = analysis.get("systemic", {})

    # =====================================================================
    # ONCELIK 1: En Yuksek Risk Durumlari
    # =====================================================================

    has_taban = any("TABAN" in a for a in critical_alerts)
    has_kritik = any("KRITIK" in a or "KRİTİK" in a for a in critical_alerts)
    has_double_liquidity = any("CIFT" in a or "ÇİFT" in a for a in critical_alerts)
    has_group_spiral = any("SARMAL" in a for a in critical_alerts)

    # ONCELIK 1A: Cift likidite kilidi
    if has_double_liquidity:
        lines.append(
            "CIFT LIKIDITE KILIDI: OZATD ve DSTKF'de eszamanli likidite daralmasi "
            "tespit edildi. Bu iki hisse fonun en buyuk pozisyonlari oldugu icin "
            "cikis imkani cok kisitli."
        )

    # ONCELIK 1B: Grup sarmali
    if has_group_spiral:
        tickers = [t.replace(".IS", "") for t in systemic.get("tickers", [])]
        tickers_str = " / ".join(tickers) if tickers else "TERA grubu"
        lines.append(
            f"GRUP SARMALI: {tickers_str} hisselerinde eszamanli sert dusus ve "
            f"yuksek korelasyon. Tera grubunda zincirleme satis baskisi olusuyor."
        )

    # ONCELIK 1C: Taban serisi
    if has_taban:
        taban_alerts = [a for a in critical_alerts if "TABAN" in a]
        stocks = [a.split(":")[0].replace(".IS", "") if ":" in a else a for a in taban_alerts]
        lines.append(
            f"TABAN SERISI: {', '.join(stocks)} hissesinde ust uste taban. "
            f"Likidite tamamen kilitlenebilir, acil durum plani gozden gecirilmeli."
        )

    # ONCELIK 1D: Yuksek stres
    if stress_level == "high" and has_kritik and not has_taban and not has_double_liquidity and not has_group_spiral:
        lines.append(
            f"YUKSEK STRES: {triggered} kural ayni anda tetiklendi. "
            f"Kritik alarmlar aktif durumda, risk seviyesi yuksek."
        )
    elif stress_level == "high" and not has_kritik and not has_double_liquidity and not has_group_spiral and not has_taban:
        lines.append(
            f"YUKSEK STRES: {triggered} kural tetiklendi ancak henuz kritik alarm yok. "
            f"Stres kurallari uyari veriyor, dikkatle izlenmeli."
        )

    # ONCELIK 1E: Net portfoy etkisi cok negatif
    if net_effect < -3.0:
        lines.append(
            f"BUGUN NET KAYIP VAR: Hisse portfoyunun agirlikli ortalamasi "
            f"%{net_effect:.2f}. Rotasyon dengelemesi yetersiz kaldi."
        )

    # =====================================================================
    # ONCELIK 2: Orta Seviye Risk Durumlari
    # =====================================================================

    if stress_level == "medium" and not lines:
        lines.append(
            f"ORTA STRES: {triggered} kural tetiklendi. "
            f"Bazi risk gostergeleri uyari seviyesinde, ancak henuz kritik degil."
        )

    # Havuz daralmasi
    if rotation is not None:
        pool = rotation.get("pool", {})
        remaining = pool.get("remaining", 5)
        pool_warning = rotation.get("pool_warning")
        if remaining < 2:
            lines.append(
                f"ROTASYON HAVUZU DARALIYOR: Taze hisse adayi sadece {remaining}. "
                f"Fon yoneticisinin rotasyon yapabilecegi yeni hisse secenegi azaliyor."
            )
        elif remaining < 3:
            lines.append(
                f"Rotasyon havuzunda {remaining} taze aday kaldi. Yakinda daralma riski var."
            )
        if pool_warning:
            lines.append(pool_warning)

    # Konsantrasyon artisi
    if stress is not None:
        conc_change = stress.get("concentration_change_30d")
        conc = stress.get("concentration_ratio")
        if conc_change is not None and conc_change > 15.0:
            lines.append(
                f"KONSANTRASYON RISKI ARTIYOR: 30 gunde %{conc_change:.1f} artis. "
                f"Ortalama yatirim basina {conc:.1f} milyon TL -- "
                f"buyuk yatirimcilara bagimlilik artiyor."
            )

    # NAV 5g art arda dusus
    if stress is not None:
        nav_down_5d = stress.get("nav_down_5d")
        if nav_down_5d:
            lines.append(
                "NAV 5 GUNDUR DUSUYOR: Fon birim fiyati ardi ardina dususte. "
                "Yatirimci panigi tetiklenmeden once izlenmeli."
            )

    # =====================================================================
    # ONCELIK 3: Sakin Gun / Olumlu Durum
    # =====================================================================

    if not lines:
        lines.append(
            "Sakin bir gun. Tum risk gostergeleri normal seviyede, "
            "kritik alarm yok."
        )
        if net_effect > 0:
            lines.append(
                f"Hisse portfoyu bugun net pozitif (%{net_effect:+.2f})."
            )
        if stress_level == "low":
            lines.append(
                "Stres testi dusuk seviyede, fon sagligi normal."
            )

    lines.append("Detaylar icin yukaridaki tablolari inceleyebilirsiniz.")

    return " ".join(lines)
