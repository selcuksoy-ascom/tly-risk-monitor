# =============================================================================
# money_flow.py - Gelismis Para Akisi Analizi Modulu
# =============================================================================
# TLY fonunun tum gecmis TEFAS verisini kullanarak net para giris/cikis
# analizi, aylik agregasyon, ivme, mevsimsel karsilastirma ve uyari
# kurallarini calistirir.
# =============================================================================

from datetime import date, timedelta
from typing import Optional, Dict, Any, List
from io import BytesIO

import pandas as pd
import numpy as np

FUND_CODE = "TLY"
FUND_KIND = "YAT"
FIRST_DATE = "2021-06-15"


def fetch_full_history() -> Optional[pd.DataFrame]:
    """TLY fonunun tum gecmis TEFAS verisini ceker (2021-06-15'ten bugune)."""
    try:
        from pytefas import Crawler
    except ImportError:
        return None

    try:
        c = Crawler()
        end = date.today()
        df = c.fetch(FIRST_DATE, end.isoformat(), kind=FUND_KIND, fund_code=FUND_CODE)
        if df is None or df.empty:
            return None
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None


def _pct_change_safe(a, b):
    """Yuzde degisim, sifira bolme korumali."""
    if b == 0 or pd.isna(b) or pd.isna(a):
        return None
    return round(((a - b) / b) * 100.0, 2)


def calc_daily_net_flow(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gunluk net para akisini hesaplar.

    net_akis = (bugun_AUM - dun_AUM) - (dun_AUM * nav_degisim_yuzdesi / 100)

    Bu formül AUM degisiminden NAV kaynakli degisimi cikararak
    gercek para giris/cikisini bulur.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    price_col = "price"
    aum_col = "portfolio_size"

    # NAV degisim yuzdesi
    df["nav_pct"] = df[price_col].pct_change() * 100
    # AUM degisimi (TL)
    df["aum_diff"] = df[aum_col].diff()

    # Net akis
    df["net_flow"] = np.nan
    for i in range(1, len(df)):
        prev_price = df[price_col].iloc[i - 1]
        curr_price = df[price_col].iloc[i]
        prev_aum = df[aum_col].iloc[i - 1]

        if prev_price > 0 and curr_price > 0 and pd.notna(prev_aum) and prev_aum > 0:
            nav_pct = ((curr_price - prev_price) / prev_price) * 100.0
            aum_from_nav = prev_aum * nav_pct / 100.0
            df.loc[df.index[i], "net_flow"] = df["aum_diff"].iloc[i] - aum_from_nav

    df["net_flow"] = df["net_flow"].astype(float)
    return df


def aggregate_monthly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Aylik agregasyon: toplam net akis, ortalama gunluk akis, AUM ve yatirimci degisimi."""
    df = daily_df.dropna(subset=["net_flow"]).copy()
    if df.empty:
        return pd.DataFrame()

    df["year_month"] = df["date"].dt.to_period("M")

    monthly = df.groupby("year_month").agg(
        total_net_flow=("net_flow", "sum"),
        avg_daily_flow=("net_flow", "mean"),
        trading_days=("net_flow", "count"),
        aum_start=("portfolio_size", "first"),
        aum_end=("portfolio_size", "last"),
        inv_start=("investor_count", "first"),
        inv_end=("investor_count", "last"),
    ).reset_index()

    monthly["year_month_str"] = monthly["year_month"].astype(str)

    monthly["aum_change_pct"] = monthly.apply(
        lambda r: _pct_change_safe(r["aum_end"], r["aum_start"]), axis=1
    )

    monthly["investor_change"] = monthly["inv_end"] - monthly["inv_start"]

    # 12 aylik hareketli ortalama
    monthly["flow_ma_12"] = (
        monthly["total_net_flow"].rolling(12, min_periods=1).mean()
    )

    return monthly


def calc_weekly_momentum(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Haftalik ivme: bu hafta ortalamasi - gecen hafta ortalamasi."""
    df = daily_df.dropna(subset=["net_flow"]).copy()
    if df.empty:
        return pd.DataFrame()

    iso = df["date"].dt.isocalendar()
    df["iso_year"] = iso["year"].astype(int)
    df["iso_week"] = iso["week"].astype(int)
    df["year_week"] = (
        df["iso_year"].astype(str) + "-W" + df["iso_week"].astype(str).str.zfill(2)
    )

    weekly = df.groupby(["iso_year", "iso_week", "year_week"]).agg(
        avg_daily_flow=("net_flow", "mean"),
        total_flow=("net_flow", "sum"),
        trading_days=("net_flow", "count"),
    ).reset_index()

    weekly = weekly.sort_values(["iso_year", "iso_week"]).reset_index(drop=True)

    # Ivme = bu hafta ortalamasi - gecen hafta ortalamasi
    weekly["momentum"] = weekly["avg_daily_flow"].diff()

    return weekly


def calc_long_term_stats(monthly_df: pd.DataFrame) -> Dict[str, Any]:
    """Uzun vade istatistikler: ortalama, en yuksek giris/cikis, mevsimsel desen, std."""
    flows = monthly_df["total_net_flow"].dropna()
    if len(flows) == 0:
        return {}

    all_time_avg = float(flows.mean())
    all_time_std = float(flows.std())

    max_idx = int(flows.idxmax())
    min_idx = int(flows.idxmin())

    # Mevsimsel desen: her ayin tarihsel ortalamasi
    mdf = monthly_df.copy()
    mdf["month_num"] = mdf["year_month"].apply(lambda x: x.month)
    seasonal = {}
    for m in range(1, 13):
        m_flows = mdf[mdf["month_num"] == m]["total_net_flow"]
        if len(m_flows) > 0:
            seasonal[m] = round(float(m_flows.mean()), 2)

AY_ISIMLERI = {
    1: "Ocak", 2: "Subat", 3: "Mart", 4: "Nisan",
    5: "Mayis", 6: "Haziran", 7: "Temmuz", 8: "Agustos",
    9: "Eylul", 10: "Ekim", 11: "Kasim", 12: "Aralik",
}


def calc_seasonal_calendar(monthly_all: pd.DataFrame) -> List[Dict[str, Any]]:
    """Her ayin tarihsel profilini cikarir: ortalama, pozitif/negatif yil sayisi, en iyi/kotu yil."""
    if monthly_all.empty:
        return []

    mdf = monthly_all.copy()
    mdf["month_num"] = mdf["year_month"].apply(lambda x: x.month)
    mdf["year"] = mdf["year_month"].apply(lambda x: x.year)

    calendar = []
    for m in range(1, 13):
        m_rows = mdf[mdf["month_num"] == m]
        if m_rows.empty:
            calendar.append({
                "month_num": m,
                "month_name": AY_ISIMLERI[m],
                "avg_flow": 0.0,
                "positive_years": 0,
                "total_years": 0,
                "best_flow": None,
                "best_year": None,
                "worst_flow": None,
                "worst_year": None,
            })
            continue

        flows = m_rows["total_net_flow"].dropna()
        if len(flows) == 0:
            calendar.append({
                "month_num": m,
                "month_name": AY_ISIMLERI[m],
                "avg_flow": 0.0,
                "positive_years": 0,
                "total_years": len(m_rows),
                "best_flow": None,
                "best_year": None,
                "worst_flow": None,
                "worst_year": None,
            })
            continue

        avg = float(flows.mean())
        pos_count = int((flows > 0).sum())
        total = len(flows)

        best_idx = int(flows.idxmax())
        worst_idx = int(flows.idxmin())

        calendar.append({
            "month_num": m,
            "month_name": AY_ISIMLERI[m],
            "avg_flow": avg,
            "positive_years": pos_count,
            "total_years": total,
            "best_flow": float(flows.iloc[best_idx]),
            "best_year": int(m_rows.iloc[best_idx]["year"]),
            "worst_flow": float(flows.iloc[worst_idx]),
            "worst_year": int(m_rows.iloc[worst_idx]["year"]),
        })

    return calendar


def _seasonal_assessment(entry: Dict[str, Any]) -> str:
    """Mevsimsel takvim degerlendirmesi uretir."""
    if entry["total_years"] == 0:
        return "➖ Veri yok"
    ratio = entry["positive_years"] / entry["total_years"]
    if ratio >= 0.8:
        return "✅ Guclu giris ayi"
    elif ratio >= 0.6:
        return "✅ Giris ayi"
    elif ratio <= 0.2:
        return "🚨 Tarihsel cikis ayi"
    elif ratio <= 0.4:
        return "⚠️ Cikis egilimli"
    else:
        return "➖ Karisik"


def current_month_highlight(
    seasonal_calendar: List[Dict], monthly_selected: pd.DataFrame
) -> str:
    """Mevcut ayin tarihsel profil ile karsilastirmasini metin olarak uretir."""
    today = date.today()
    curr_month = today.month
    curr_month_name = AY_ISIMLERI.get(curr_month, str(curr_month))

    entry = next((e for e in seasonal_calendar if e["month_num"] == curr_month), None)
    if entry is None or monthly_selected.empty:
        return ""

    curr_row = monthly_selected[monthly_selected["year_month"].apply(lambda x: x.month == curr_month)]
    if curr_row.empty:
        return ""

    curr_flow = float(curr_row.iloc[-1]["total_net_flow"])
    hist_avg = entry["avg_flow"]
    hist_pos = entry["positive_years"]
    hist_tot = entry["total_years"]

    if hist_tot == 0:
        return f"{curr_month_name} ayı için yeterli tarihsel veri yok."

    status_icon = "✅" if curr_flow >= 0 else "⚠️"
    flow_str = f"{curr_flow/1e9:+.1f} milyar"

    if hist_avg > 0 and curr_flow >= 0:
        return (
            f"{curr_month_name} tarihsel olarak giriş ayı ({hist_pos}/{hist_tot} yıl pozitif).\n\n"
            f"Bu yıl {curr_month_name}: {flow_str} → ✅ Tarihe uygun"
        )
    elif hist_avg > 0 and curr_flow < 0:
        return (
            f"{curr_month_name} tarihsel olarak giriş ayı ({hist_pos}/{hist_tot} yıl pozitif).\n\n"
            f"Bu yıl {curr_month_name}: {flow_str} → ⚠️ Tarihe aykırı"
        )
    elif hist_avg <= 0 and curr_flow < 0:
        return (
            f"{curr_month_name} tarihsel olarak çıkış ayı ({hist_pos}/{hist_tot} yıl pozitif).\n\n"
            f"Bu yıl {curr_month_name}: {flow_str} → 📅 Mevsimsel çıkış"
        )
    else:
        return (
            f"{curr_month_name} tarihsel olarak çıkış ayı ({hist_pos}/{hist_tot} yıl pozitif).\n\n"
            f"Bu yıl {curr_month_name}: {flow_str} → ✅ Tarihe rağmen giriş"
        )


def generate_commentary(
    comp: Dict[str, Any],
    warnings: list,
    momentum_selected: pd.DataFrame,
    seasonal_calendar: list,
    monthly_selected: pd.DataFrame,
) -> str:
    """Kural tabanli tek paragraf akilli yorum uretir."""
    period_avg = comp.get("period_avg", 0)
    all_time_avg = comp.get("all_time_avg", 0)
    all_time_std = comp.get("all_time_std", 0) or 1
    z_score = comp.get("z_score")

    # Son 4 hafta ivme yonu
    mom = momentum_selected.dropna(subset=["momentum"])
    momentum_status = "yatay"
    if len(mom) >= 4:
        last_4 = mom["momentum"].tail(4)
        if all(last_4.iloc[i] < last_4.iloc[i + 1] for i in range(len(last_4) - 1)):
            momentum_status = "yükseliyor"
        elif all(last_4.iloc[i] > last_4.iloc[i + 1] for i in range(len(last_4) - 1)):
            momentum_status = "düşüyor"

    # Anomali var mi?
    has_seasonal_anomaly = any("Mevsimsel anomali" in w for w in warnings)

    pct_str = ""
    if all_time_avg != 0:
        pct_up = abs((period_avg - all_time_avg) / abs(all_time_avg)) * 100
        pct_str = f"uzun vade ortalamasının %{pct_up:.0f} "

    lines = []

    if period_avg > 0 and momentum_status == "yükseliyor":
        lines.append(
            f"Fona para girişi ivme kazanıyor, "
            f"{pct_str}{'üstünde' if period_avg > all_time_avg else 'altında'} seyrediyor."
        )
    elif period_avg > 0 and momentum_status == "düşüyor":
        losing_weeks = 0
        if len(mom) >= 2:
            rev = mom["momentum"].iloc[::-1]
            for i in range(1, len(rev)):
                if rev.iloc[i] > rev.iloc[i - 1]:
                    losing_weeks += 1
                else:
                    break
        lines.append(
            f"Fona giriş devam ediyor ancak ivme kaybediyor. "
            f"Son {max(losing_weeks, 1)} haftadır yavaşlama var. Dikkat."
        )
    elif period_avg < 0:
        sigma_str = f"{abs(z_score):.1f} sigma" if z_score is not None else "anlamlı ölçüde"
        lines.append(
            f"Fondan net para çıkışı var. "
            f"Bu ayki çıkış tarihsel ortalamanın {sigma_str} {'altında' if z_score and z_score < 0 else 'üstünde'}."
        )
    else:
        lines.append(
            f"Fon akışı uzun vade ortalamasına yakın seyrediyor. "
            f"İvme {momentum_status}."
        )

    if has_seasonal_anomaly:
        lines.append(
            "Bu dönem tarihsel olarak giriş ayı olmasına rağmen "
            "çıkış görülüyor — anormal bir durum."
        )

    return " ".join(lines)


def export_to_excel(
    monthly_selected: pd.DataFrame,
    seasonal_calendar: list,
    momentum_selected: pd.DataFrame,
) -> BytesIO:
    """Aylik akis tablosunu ve mevsimsel takvimi Excel olarak disari aktarir."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1: Aylik Akis
        if not monthly_selected.empty:
            exp = monthly_selected[[
                "year_month_str", "total_net_flow", "aum_change_pct",
                "investor_change", "trading_days",
            ]].copy()
            exp.columns = [
                "Ay", "Net Akis (TL)", "AUM Degisimi (%)",
                "Yatirimci Degisimi", "Islem Gunu",
            ]
            exp["Net Akis (Milyar TL)"] = exp["Net Akis (TL)"] / 1e9
            exp = exp.drop(columns=["Net Akis (TL)"])
            exp.to_excel(writer, sheet_name="Aylik Akis", index=False)

        # Sheet 2: Mevsimsel Takvim
        cal_df = pd.DataFrame(seasonal_calendar)
        if not cal_df.empty:
            cal_df["Ortalama (Milyar TL)"] = cal_df["avg_flow"] / 1e9
            cal_df["Pozitif Orani"] = cal_df.apply(
                lambda r: f"{r['positive_years']}/{r['total_years']}", axis=1
            )
            cal_df = cal_df[[
                "month_name", "Ortalama (Milyar TL)", "Pozitif Orani",
                "best_year", "worst_year",
            ]]
            cal_df.columns = [
                "Ay", "Tarihsel Ort (Milyar TL)", "Pozitif Yil / Toplam",
                "En Iyi Yil", "En Kotu Yil",
            ]
            cal_df.to_excel(writer, sheet_name="Mevsimsel Takvim", index=False)

        # Sheet 3: Haftalik Ivme
        if not momentum_selected.empty:
            mom_exp = momentum_selected[[
                "year_week", "avg_daily_flow", "momentum",
            ]].copy()
            mom_exp.columns = ["Hafta", "Ort Gunluk Akis", "Ivme"]
            mom_exp["Ort Gunluk Akis (Milyar TL)"] = mom_exp["Ort Gunluk Akis"] / 1e9
            mom_exp["Ivme (Milyar TL)"] = mom_exp["Ivme"] / 1e9
            mom_exp = mom_exp.drop(columns=["Ort Gunluk Akis", "Ivme"])
            mom_exp.to_excel(writer, sheet_name="Haftalik Ivme", index=False)

    output.seek(0)
    return output


def analyze_money_flow(
    monthly_all: pd.DataFrame,
    momentum_full: pd.DataFrame,
    selected_monthly: pd.DataFrame,
    long_term: Dict[str, Any],
) -> list:
    """Uyari kurallarini calistirir (KURAL 1-4)."""
    warnings = []

    if selected_monthly.empty or not long_term:
        return warnings

    current = selected_monthly.iloc[-1]
    curr_month_period = current["year_month"]
    curr_month_num = curr_month_period.month
    curr_year = curr_month_period.year
    curr_flow = float(current["total_net_flow"])

    # KURAL 1 & 2: Mevsimsel karsilastirma (gecen yilin ayni ayi)
    prev_mask = monthly_all["year_month"].apply(
        lambda x: x.year == curr_year - 1 and x.month == curr_month_num
    )
    prev_same = monthly_all[prev_mask]
    if not prev_same.empty:
        prev_flow = float(prev_same["total_net_flow"].iloc[0])
        if prev_flow < 0 and curr_flow < 0:
            warnings.append(
                "📅 Mevsimsel çıkış olabilir, geçen yıl da aynı dönemde çıkış vardı"
            )
        elif prev_flow > 0 and curr_flow < 0:
            warnings.append(
                "⚠️ Mevsimsel anomali: Geçen yıl bu dönem girişti, bu yıl çıkış var"
            )

    # KURAL 3: Ivme kaybi (3 hafta ust uste dusus)
    mf = momentum_full.dropna(subset=["momentum"])
    if len(mf) >= 3:
        last_3 = mf["momentum"].tail(3)
        decreasing = all(
            last_3.iloc[i] > last_3.iloc[i + 1] for i in range(len(last_3) - 1)
        )
        if decreasing and last_3.iloc[-1] < 0:
            warnings.append("⚠️ ERKEN UYARI: 3 haftadır giriş ivmesi düşüyor")

    # KURAL 4: Tarihsel dislik (2 std sapma altinda)
    avg = long_term.get("all_time_avg", 0)
    std = long_term.get("all_time_std", 0)
    if std > 0 and curr_flow < avg - 2 * std:
        warnings.append("🚨 TARİHSEL DIŞLIK: Bu seviye çok nadir görülüyor")

    return warnings


def calc_comparison(
    selected_monthly: pd.DataFrame, long_term: Dict[str, Any]
) -> Dict[str, Any]:
    """Secilen donem ile uzun vade ortalamasini karsilastirir."""
    if selected_monthly.empty or not long_term:
        return {}

    period_avg = float(selected_monthly["total_net_flow"].mean())
    all_time_avg = long_term.get("all_time_avg", 0)
    all_time_std = long_term.get("all_time_std", 0)

    pct_diff = None
    if all_time_avg != 0:
        pct_diff = round(((period_avg - all_time_avg) / abs(all_time_avg)) * 100, 1)

    # Degerlendirme
    if period_avg < 0:
        assessment = "🚨 Net çıkış"
    elif pct_diff is not None and pct_diff < -50:
        assessment = "⚠️ Normalin altında"
    elif pct_diff is not None and pct_diff > 50:
        assessment = "✅ Normal üstünde"
    else:
        assessment = "✅ Normal seviyede"

    # Aylik standart sapma karsilastirmasi
    z_score = None
    if all_time_std > 0:
        z_score = round((period_avg - all_time_avg) / all_time_std, 2)

    return {
        "period_avg": period_avg,
        "all_time_avg": all_time_avg,
        "pct_diff": pct_diff,
        "assessment": assessment,
        "z_score": z_score,
    }


def analyze_money_flow(
    df: pd.DataFrame,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """
    Gelismis para akisi analizi.

    Args:
        df: TEFAS ham verisi (tum gecmis, fetch_full_history() ciktisi)
        period_start: Analiz donemi baslangici (None = tum veri)
        period_end: Analiz donemi bitisi (None = tum veri)

    Returns:
        {
            'daily': secili donem gunluk net akis DataFrame'i,
            'monthly_all': tum veri aylik agregasyon,
            'monthly_selected': secili donem aylik agregasyon,
            'momentum_full': tum veri haftalik ivme,
            'momentum_selected': secili donem haftalik ivme,
            'long_term': uzun vade istatistikler,
            'seasonal_calendar': 12 aylik mevsimsel takvim listesi,
            'warnings': uyari mesajlari listesi,
            'comparison': karsilastirma metrikleri,
            'commentary': akilli yorum metni,
        }
    """
    if df is None or df.empty:
        return None

    try:
        # Tum veri uzerinden gunluk net akis hesapla
        daily_full = calc_daily_net_flow(df)

        # Aylik agregasyon (tum veri)
        monthly_all = aggregate_monthly(daily_full)

        # Haftalik ivme (tum veri — uyarilar icin)
        momentum_full = calc_weekly_momentum(daily_full)

        # Uzun vade istatistikler
        long_term = calc_long_term_stats(monthly_all)

        # --- Secili donem filtrelemesi ---
        daily_sel = daily_full.copy()
        if period_start:
            daily_sel = daily_sel[daily_sel["date"] >= pd.Timestamp(period_start)]
        if period_end:
            daily_sel = daily_sel[daily_sel["date"] <= pd.Timestamp(period_end)]

        monthly_selected = aggregate_monthly(daily_sel)
        momentum_selected = calc_weekly_momentum(daily_sel)

        # Uyarilar (tum veri baglaminda, son ay uzerinden)
        warnings = generate_warnings(
            monthly_all, momentum_full, monthly_selected, long_term
        )

        # Mevsimsel takvim
        seasonal_calendar = calc_seasonal_calendar(monthly_all)

        # Karsilastirma
        comparison = calc_comparison(monthly_selected, long_term)

        # Akilli yorum
        commentary = generate_commentary(
            comparison, warnings, momentum_selected,
            seasonal_calendar, monthly_selected,
        )

        return {
            "daily": daily_sel,
            "monthly_all": monthly_all,
            "monthly_selected": monthly_selected,
            "momentum_full": momentum_full,
            "momentum_selected": momentum_selected,
            "long_term": long_term,
            "seasonal_calendar": seasonal_calendar,
            "warnings": warnings,
            "comparison": comparison,
            "commentary": commentary,
        }
    except Exception:
        return None
