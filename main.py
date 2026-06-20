#!/usr/bin/env python3
# =============================================================================
# main.py - TLY Risk Analiz Aracı - Ana Giriş Noktası
# =============================================================================
# Çalıştır: python main.py
# =============================================================================

import sys
import os
from datetime import date

# Modüllerin tly_risk klasöründen import edilmesini sağla
sys.path.insert(0, os.path.dirname(__file__))

from colorama import init, Fore, Style

init(autoreset=True)

C_CYAN   = Fore.CYAN + Style.BRIGHT
C_YELLOW = Fore.YELLOW + Style.BRIGHT
C_GREEN  = Fore.GREEN + Style.BRIGHT
C_WHITE  = Fore.WHITE + Style.BRIGHT
C_RESET  = Style.RESET_ALL


def ask_portfolio_update() -> bool:
    """
    KAP raporu güncellemesi sorusunu sorar.
    'e' → True (güncelleme yapılacak)
    'h' veya Enter → False
    """
    print()
    print(C_YELLOW + "=" * 56 + C_RESET)
    print(C_YELLOW + "  TLY Risk Analiz Aracı  |  v1.0" + C_RESET)
    print(C_YELLOW + "=" * 56 + C_RESET)
    print()

    answer = input(
        C_WHITE + "  Son KAP raporuna göre portföyde değişiklik var mı? (e/h): " + C_RESET
    ).strip().lower()

    return answer in ("e", "evet", "y", "yes")


def guide_config_update() -> None:
    """Kullanıcıya config.py güncelleme talimatı verir."""
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.py"))

    print()
    print(C_CYAN + "  ─────────────────────────────────────────────────────" + C_RESET)
    print(C_CYAN + "  PORTFÖY GÜNCELLEME TALİMATI" + C_RESET)
    print(C_CYAN + "  ─────────────────────────────────────────────────────" + C_RESET)
    print(f"  Dosya: {config_path}")
    print()
    print("  1. config.py dosyasını bir metin editörüyle açın.")
    print("  2. PORTFOLIO sözlüğünde değişen hisseleri güncelleyin:")
    print()
    print('     Örnek:')
    print('       "DSTKF.IS": {')
    print('           "name": "Destek Faktoring",')
    print('           "weight": 18.50,           ← YENİ AĞIRLIK')
    print('           "category": "anchor",')
    print('           "prev_weight": 17.71,       ← ESKİ AĞIRLIĞI BURAYA TAŞI')
    print('       },')
    print()
    print("  3. EQUITY_RATIO değerini de güncelleyin.")
    print("  4. Dosyayı kaydedin ve bu programı yeniden çalıştırın.")
    print()
    print(C_CYAN + "  ─────────────────────────────────────────────────────" + C_RESET)

    input(C_YELLOW + "\n  Güncellemeleri yaptıysanız Enter'a basarak devam edin... " + C_RESET)


def main() -> None:
    """Ana program akışı."""

    # ----- ADIM 1: KAP Raporu Güncelleme -----
    needs_update = ask_portfolio_update()

    if needs_update:
        guide_config_update()

    # ----- ADIM 2: Config yükle -----
    try:
        from config import PORTFOLIO, EQUITY_RATIO, DEFAULT_CAPITAL, PANIC_RATE
    except ImportError as e:
        print(f"\n  [HATA] config.py okunamadı: {e}")
        sys.exit(1)

    # ----- ADIM 3: Anapara girişi -----
    from simulator import get_capital_from_user
    capital = get_capital_from_user()

    # ----- ADIM 4: Veri çek -----
    print()
    print(C_WHITE + "  Veriler yükleniyor, lütfen bekleyin..." + C_RESET)

    from data_fetcher import fetch_all_portfolio_data
    portfolio_data = fetch_all_portfolio_data(PORTFOLIO)

    # ----- ADIM 4b: TEFAS fon sağlığı (risk analizinden önce) -----
    from tefas_fetcher import analyze_fund_health
    fund_health = analyze_fund_health()

    # ----- ADIM 5: Risk analizi -----
    print()
    print(C_WHITE + "  Risk analizi yapılıyor..." + C_RESET)

    from risk_analyzer import analyze_portfolio
    analysis = analyze_portfolio(portfolio_data, fund_health=fund_health)

    # ----- ADIM 6: Simülasyon -----
    from simulator import run_simulation
    sim_result = run_simulation(
        capital=capital,
        equity_ratio=EQUITY_RATIO,
        panic_rate=PANIC_RATE,
    )

    # ----- ADIM 7: Stres Testi -----
    from stress_test import analyze_stress_test
    stress_result = analyze_stress_test()

    # Stres testinden gelen kritik uyarilari ana uyarilara ekle
    if stress_result:
        for w in stress_result.get("warnings", []):
            if "KRITIK" in w or "SISTEMIK" in w:
                analysis["critical_alerts"].append(w)

    # ----- ADIM 8: Rotasyon Analizi -----
    from rotation_tracker import analyze_rotation
    rotation_result = analyze_rotation()

    # ----- ADIM 9: Raporu yazdır -----
    from reporter import (
        print_header,
        print_net_portfolio_effect,
        print_risk_table,
        print_systemic_risk,
        print_simulation,
        print_fund_health,
        print_stress_test,
        print_rotation_analysis,
        print_critical_alerts,
        print_footer,
    )

    print_header(report_date=date.today())
    print_net_portfolio_effect(analysis["per_stock"])
    print_risk_table(analysis["per_stock"])
    print_systemic_risk(analysis["systemic"])
    print_fund_health(fund_health)
    print_stress_test(stress_result)
    print_rotation_analysis(rotation_result)
    print_simulation(sim_result)
    print_critical_alerts(analysis["critical_alerts"], analysis["rotation_logs"], analysis["thin_market_alerts"])
    print_footer()

    # ----- ADIM 10: Özet çıkış kodu -----
    if analysis["critical_alerts"]:
        sys.exit(1)  # CI/monitoring için non-zero exit


if __name__ == "__main__":
    main()
