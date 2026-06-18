# =============================================================================
# app.py — TLY Risk Analiz Aracı (Streamlit Web Arayüzü)
# =============================================================================
# Çalıştır: streamlit run app.py
# Tarayıcıda http://localhost:8501 adresinde açılır.
# =============================================================================

import sys
import os
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from config import (
    PORTFOLIO, EQUITY_RATIO, DEFAULT_CAPITAL, PANIC_RATE,
    GROUP_TICKERS, CORRELATION_THRESHOLD,
)
from data_fetcher import fetch_all_portfolio_data
from risk_analyzer import analyze_portfolio
from simulator import run_simulation
from tefas_fetcher import analyze_fund_health
from stress_test import analyze_stress_test
from money_flow import (
    fetch_full_history, analyze_money_flow,
    export_to_excel, current_month_highlight,
)
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Sayfa yapılandırması
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TLY Risk Analiz Aracı",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Stil
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1a73e8; margin-bottom: 0; }
    .sub-header  { font-size: 0.95rem; color: #5f6368; margin-top: 0; }
    .metric-card { background: #f8f9fa; border-radius: 12px; padding: 1rem; text-align: center; }
    hr { margin: 0.5rem 0; }
    .risk-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    .risk-table th { color: #AAAAAA; text-align: left; padding: 8px 10px; border-bottom: 1px solid #333; font-weight: 600; }
    .risk-table td { padding: 6px 10px; border-bottom: 1px solid #2A2A2A; }
    .row-normal  td { background: #1E1E1E; color: #FFFFFF !important; }
    .row-warning td { background: #3D2B00; color: #FFD700 !important; }
    .row-fund    td { background: #0D2137; color: #60B4FF !important; }
    .row-critical td { background: #3D0000; color: #FF6B6B !important; }
    .row-error   td { background: #1E1E1E; color: #888888 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Cache: veri çekme (5 dakika TTL)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_data_cached():
    """Portföy verisini çeker, 5 dakika cache'ler."""
    return fetch_all_portfolio_data(PORTFOLIO)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_tefas_full_history():
    """TLY fonunun tum gecmis TEFAS verisini ceker, 1 saat cache'ler."""
    return fetch_full_history()


# ---------------------------------------------------------------------------
# Sidebar — Parametreler
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚙️ Parametreler")

    capital = st.number_input(
        "Anapara (TL)",
        min_value=10_000,
        max_value=100_000_000,
        value=DEFAULT_CAPITAL,
        step=10_000,
        format="%d",
        help="Portföyün toplam değeri. Enter = 500.000 TL",
    )

    equity_ratio = st.slider(
        "Hisse Oranı (%)",
        min_value=0.0,
        max_value=100.0,
        value=EQUITY_RATIO,
        step=0.1,
        help="Fonun hisse senedi ağırlığı (KAP'tan güncelleyin)",
    )

    panic_rate = st.slider(
        "Panik Senaryosu (%/gün)",
        min_value=1.0,
        max_value=25.0,
        value=PANIC_RATE,
        step=0.5,
        help="T+2 valör simülasyonunda günlük kayıp oranı",
    )

    st.markdown("---")

    st.markdown("### 📅 Para Akışı Analiz Dönemi")
    mf_period = st.radio(
        "Dönem seçin",
        ["Son 60 gün", "6 Ay", "1 Yıl", "3 Yıl", "Tümü", "Özel tarih"],
        index=0,
        horizontal=False,
    )

    today = date.today()
    if mf_period == "Son 60 gün":
        mf_start = today - timedelta(days=60)
        mf_end = today
    elif mf_period == "6 Ay":
        mf_start = today - timedelta(days=180)
        mf_end = today
    elif mf_period == "1 Yıl":
        mf_start = today - timedelta(days=365)
        mf_end = today
    elif mf_period == "3 Yıl":
        mf_start = today - timedelta(days=3 * 365)
        mf_end = today
    elif mf_period == "Tümü":
        mf_start = None
        mf_end = None
    else:
        c1, c2 = st.columns(2)
        with c1:
            mf_start = st.date_input("Başlangıç", today - timedelta(days=60))
        with c2:
            mf_end = st.date_input("Bitiş", today)

    show_seasonal_ref = st.toggle(
        "Mevsimsel Referans Çizgileri",
        value=True,
        help="Grafiklerde her ayın tarihsel ortalamasını referans çizgisi olarak göster",
    )

    st.markdown("---")

    # KAP güncelleme hatırlatıcısı
    st.markdown("### 📅 Portföy Güncelleme")
    st.caption(f"Son güncelleme: **8 Haziran 2026**")
    st.caption("KAP raporu sonrası `config.py` dosyasını güncelleyin.")

    st.markdown("---")

    st.markdown("### 🔄 Veri Yenileme")
    if st.button("🔄 Veriyi Yeniden Çek", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption("Veriler Yahoo Finance'den ~15 dk gecikmeli gelir.")

# ---------------------------------------------------------------------------
# Ana Sayfa — Başlık
# ---------------------------------------------------------------------------
st.markdown(
    f'<p class="main-header">📊 TLY Risk Analiz Raporu</p>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<p class="sub-header">Tera Portföy Birinci Serbest Fon  ·  {date.today().strftime("%d %B %Y")}</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Veri çek ve analiz et
# ---------------------------------------------------------------------------
with st.spinner("📡 Yahoo Finance'den veri çekiliyor... Lütfen bekleyin."):
    portfolio_data = fetch_data_cached()

if portfolio_data is None:
    st.error("Veri çekilemedi. İnternet bağlantınızı kontrol edin.")
    st.stop()

analysis = analyze_portfolio(portfolio_data)
sim = run_simulation(capital=capital, equity_ratio=equity_ratio, panic_rate=panic_rate)

# ---------------------------------------------------------------------------
# Özet metrikler
# ---------------------------------------------------------------------------
st.markdown("### 🧮 Portföy Özeti")

col1, col2, col3, col4, col5 = st.columns(5)

total_weight = sum(d["weight"] for d in analysis["per_stock"].values())
critical_count = sum(1 for d in analysis["per_stock"].values() if d.get("is_critical"))
has_systemic = analysis["systemic"]["is_critical"]
data_ok = sum(1 for d in portfolio_data.values() if not d.get("error"))

with col1:
    st.metric("Toplam Hisse", f"{total_weight:.1f}%")
with col2:
    st.metric("Veri Gelen", f"{data_ok}/{len(PORTFOLIO)}")
with col3:
    st.metric("Kritik Hisseler", critical_count, delta=None,
              delta_color="inverse" if critical_count == 0 else "off")
with col4:
    st.metric("Sistemik Risk",
              "🔴 Var" if has_systemic else "🟢 Yok")
with col5:
    st.metric("Hisse Değeri (Gün 0)", f"{sim['daily_equity_values'][0]:,.0f} ₺")

# ---------------------------------------------------------------------------
# Risk tablosu
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 📋 Risk Skoru Tablosu")

# Satır tipine göre CSS class'ı belirle
def _row_class(is_critical, is_rotation, is_thin, is_fund, is_error):
    if is_critical:
        return "row-critical"
    elif is_rotation:
        return "row-critical"  # rotasyon kritik değil ama yine de dikkat çekici
    elif is_thin:
        return "row-warning"
    elif is_fund:
        return "row-fund"
    elif is_error:
        return "row-error"
    else:
        return "row-normal"

headers = ["Hisse", "Ad", "Ağırlık", "Fiyat (₺)", "Değişim", "Hacim/Ort", "Durum"]

html = '<table class="risk-table"><thead><tr>'
for h in headers:
    html += f"<th>{h}</th>"
html += "</tr></thead><tbody>"

for ticker, data in analysis["per_stock"].items():
    short = ticker.replace(".IS", "")
    name = data.get("name", "?")
    weight = data["weight"]
    price = data.get("price")
    change_pct = data.get("change_pct")
    vol_ratio = data.get("volume_ratio")
    liq_status = data.get("liquidity_status", "Normal")
    is_critical = data.get("is_critical", False)
    is_rotation = data.get("is_rotation", False)
    is_thin = data.get("is_thin_market", False)
    is_fund = data.get("is_fund", False)
    is_error = data.get("error", False)

    price_str = f"{price:,.4f}" if price is not None else ("---" if is_fund else "—")
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else ("---" if is_fund else "—")
    vol_str = f"%{vol_ratio:.0f}" if vol_ratio is not None else ("---" if is_fund else "—")

    if is_critical:
        status_icon = "🔴"
    elif is_rotation:
        status_icon = "🔵"
    elif is_thin:
        status_icon = "🟡"
    elif is_fund:
        status_icon = "🔷"
    elif is_error:
        status_icon = "⚫"
    else:
        status_icon = "🟢"

    css_class = _row_class(is_critical, is_rotation, is_thin, is_fund, is_error)

    html += f'<tr class="{css_class}">'
    html += f"<td>{short}</td>"
    html += f"<td>{name}</td>"
    html += f"<td>%{weight:.2f}</td>"
    html += f"<td>{price_str}</td>"
    html += f"<td>{change_str}</td>"
    html += f"<td>{vol_str}</td>"
    html += f"<td>{status_icon} {liq_status}</td>"
    html += "</tr>"

html += "</tbody></table>"

st.markdown(html, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sistemik Risk
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 🔗 Sistemik Risk Analizi")

s = analysis["systemic"]
corr = s.get("correlation")
tickers_str = " / ".join(t.replace(".IS", "") for t in s.get("tickers", []))

col_a, col_b = st.columns([1, 2])

with col_a:
    if corr is not None:
        delta_str = f"Eşik: {CORRELATION_THRESHOLD:.2f}"
        st.metric(
            f"Grup Korelasyonu ({tickers_str})",
            f"{corr:.3f}",
            delta=f"{(corr - CORRELATION_THRESHOLD)*100:.0f} bp",
            delta_color="inverse" if corr <= CORRELATION_THRESHOLD else "normal",
        )
    else:
        st.metric(f"Grup Korelasyonu ({tickers_str})", "Hesaplanamadı")

with col_b:
    if corr is not None:
        import math
        safe_corr = corr if (isinstance(corr, (int, float)) and not math.isnan(corr)) else 0.0
        clamped = max(0.0, min(1.0, safe_corr))
        st.progress(clamped, text=f"Korelasyon: {safe_corr:.2f}")
    if s["is_critical"]:
        st.error("⚠️ KRİTİK: Döngüsel sermaye yapısında bozulma!")
    elif corr and corr > CORRELATION_THRESHOLD:
        st.warning("⚡ Korelasyon yüksek, ancak bugünkü yön aynı değil.")
    else:
        st.success("✅ Grup korelasyonu normal seviyede.")

# ---------------------------------------------------------------------------
# T+2 Valör Simülasyonu
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 💸 T+2 Valör Simülasyonu")

evals = sim["daily_equity_values"]
loss_tl = sim["equity_loss_tl"]
loss_pct = sim["equity_loss_pct"]
remaining = sim["remaining_portfolio"]
non_eq = sim["non_equity_value"]

st.markdown(f"**Anapara:** {capital:,.0f} ₺  ·  **Panik Oranı:** %{panic_rate:.1f}/gün")
st.markdown("")

g1, g2, g3 = st.columns(3)

with g1:
    st.metric("Gün 0 (Hisse Değeri)", f"{evals[0]:,.0f} ₺")
with g2:
    st.metric("Gün 1", f"{evals[1]:,.0f} ₺", delta=f"-{evals[0] - evals[1]:,.0f} ₺")
with g3:
    st.metric("Gün 2 (T+2)", f"{evals[2]:,.0f} ₺", delta=f"-{evals[1] - evals[2]:,.0f} ₺")

st.markdown("")

r1, r2, r3 = st.columns(3)
with r1:
    st.metric("Toplam Hisse Kaybı", f"{loss_tl:,.0f} ₺",
              delta=f"%{loss_pct:.1f}", delta_color="inverse")
with r2:
    st.metric("Hisse Dışı Varlık (sabit)", f"{non_eq:,.0f} ₺")
with r3:
    st.metric("Kalan Toplam Portföy", f"{remaining:,.0f} ₺",
              delta=f"-{capital - remaining:,.0f} ₺", delta_color="inverse")

# ---------------------------------------------------------------------------
# Uyarılar
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 🚨 Uyarılar & Loglar")

critical_alerts = analysis.get("critical_alerts", [])
rotation_logs = analysis.get("rotation_logs", [])
thin_market_alerts = analysis.get("thin_market_alerts", [])

if not critical_alerts and not rotation_logs and not thin_market_alerts:
    st.success("✅ Bugün için kritik uyarı yok.")
else:
    for alert in critical_alerts:
        st.error(f"🔴 {alert}")
    for alert in thin_market_alerts:
        st.warning(f"🟡 {alert}")
    for log in rotation_logs:
        st.info(f"🔵 {log}")

# ---------------------------------------------------------------------------
# Fon Sağlığı (TEFAS)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 🏥 Fon Sağlığı (TEFAS)")

fund_health = analyze_fund_health()

if fund_health is None:
    st.caption("TEFAS verisi şu anda çekilemiyor.")
else:
    nav = fund_health.get("nav")
    nav_change = fund_health.get("nav_change")
    aum = fund_health.get("aum")
    aum_change_7d = fund_health.get("aum_change_7d")
    inv = fund_health.get("investor_count")
    inv_change_7d = fund_health.get("investor_change_7d")
    trend = fund_health.get("trend", "flat")

    fc1, fc2, fc3 = st.columns(3)

    with fc1:
        if nav is not None:
            delta_str = f"{nav_change:+.2f}%" if nav_change is not None else None
            st.metric("NAV Fiyatı", f"{nav:,.4f} ₺", delta=delta_str)
        else:
            st.metric("NAV Fiyatı", "Veri yok")

    with fc2:
        if aum is not None:
            aum_display = f"{aum/1e9:.1f} milyar ₺"
            delta_str = f"{aum_change_7d:+.1f}% haftalık" if aum_change_7d is not None else None
            st.metric("Fon Büyüklüğü", aum_display, delta=delta_str,
                      delta_color="normal" if (aum_change_7d is None or aum_change_7d >= 0) else "inverse")
        else:
            st.metric("Fon Büyüklüğü", "Veri yok")

    with fc3:
        if inv is not None:
            inv_display = f"{inv:,}"
            delta_str = f"{inv_change_7d:+.0f} haftalık" if inv_change_7d is not None else None
            st.metric("Yatırımcı Sayısı", inv_display, delta=delta_str,
                      delta_color="normal" if (inv_change_7d is None or inv_change_7d >= 0) else "inverse")
        else:
            st.metric("Yatırımcı Sayısı", "Veri yok")

    # Trend satırı
    trend_icon = {"up": "↗ Büyüyor", "down": "↘ Daralıyor", "flat": "→ Yatay"}
    st.caption(f"**30G Trend:** {trend_icon.get(trend, trend)}")

    # Uyarılar
    for w in fund_health.get("warnings", []):
        if "KRİTİK" in w:
            st.error(w)
        else:
            st.warning(w)

# ---------------------------------------------------------------------------
# Stres Testi & Fon Sağlığı
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 🧪 Stres Testi & Fon Sağlığı")

stress = analyze_stress_test()

if stress is None:
    st.caption("Stres testi verisi şu anda çekilemiyor (TEFAS veya Fonoloji erişilemez).")
else:
    nav = stress.get("nav")
    nav_change = stress.get("nav_change")
    aum = stress.get("aum")
    aum_change_7d = stress.get("aum_change_7d")
    inv = stress.get("investor_count")
    inv_change_7d = stress.get("investor_change_7d")
    repo_ratio = stress.get("repo_ratio")
    cash_buffer = stress.get("cash_buffer")
    coverable_exit = stress.get("coverable_exit")
    nav_trend = stress.get("nav_trend", "flat")
    stress_level = stress.get("stress_level", "low")
    warnings = stress.get("warnings", [])

    sc1, sc2, sc3 = st.columns(3)

    with sc1:
        if nav is not None:
            delta_str = f"{nav_change:+.2f}% bugün" if nav_change is not None else None
            st.metric("NAV Fiyatı", f"{nav:,.4f} ₺", delta=delta_str)
        else:
            st.metric("NAV Fiyatı", "Veri yok")

    with sc2:
        if aum is not None:
            aum_display = f"{aum/1e9:.1f} milyar ₺"
            delta_str = f"{aum_change_7d:+.1f}% haftalık" if aum_change_7d is not None else None
            st.metric("Fon Büyüklüğü (AUM)", aum_display, delta=delta_str,
                      delta_color="normal" if (aum_change_7d is None or aum_change_7d >= 0) else "inverse")
        else:
            st.metric("Fon Büyüklüğü (AUM)", "Veri yok")

    with sc3:
        if inv is not None:
            inv_display = f"{inv:,}"
            delta_str = f"{inv_change_7d:+.0f} haftalık" if inv_change_7d is not None else None
            st.metric("Yatırımcı Sayısı", inv_display, delta=delta_str,
                      delta_color="normal" if (inv_change_7d is None or inv_change_7d >= 0) else "inverse")
        else:
            st.metric("Yatırımcı Sayısı", "Veri yok")

    # Nakit tamponu ve karşılanabilir çıkış
    sc4, sc5 = st.columns(2)

    with sc4:
        if repo_ratio is not None:
            cash_display = f"%{repo_ratio:.2f} ters repo"
            if cash_buffer is not None:
                cash_display += f"  (~{cash_buffer/1e9:.1f} milyar ₺)"
            st.metric("Nakit Tamponu", cash_display)
        else:
            st.metric("Nakit Tamponu", "Fonoloji verisi yok")

    with sc5:
        if coverable_exit is not None:
            st.metric("Karşılanabilir Çıkış", f"%{coverable_exit:.2f}",
                      help="Yatırımcıların aynı anda çıkabileceği maksimum oran")
        else:
            st.metric("Karşılanabilir Çıkış", "N/A")

    # NAV Trend
    trend_icon = {"up": "↗ Yükseliyor", "down": "↘ Düşüyor", "flat": "→ Yatay"}
    st.caption(f"**NAV Trend (5 gün):** {trend_icon.get(nav_trend, nav_trend)}")

    # Stres Seviyesi
    st.markdown("#### Stres Seviyesi")
    if stress_level == "high":
        st.error("🚨 YÜKSEK — Birden fazla risk göstergesi alarm veriyor")
    elif stress_level == "medium":
        st.warning("⚠️ ORTA — Bazı risk göstergeleri uyarı seviyesinde")
    else:
        st.success("✅ DÜŞÜK — Risk göstergeleri normal seviyede")

    # Uyarılar
    if warnings:
        for w in warnings:
            if "KRİTİK" in w or "SİSTEMİK" in w:
                st.error(w)
            else:
                st.warning(w)

# ---------------------------------------------------------------------------
# Gelişmiş Para Akışı Analizi
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 💰 Gelişmiş Para Akışı Analizi")

tefas_full = fetch_tefas_full_history()

if tefas_full is None or tefas_full.empty:
    st.warning("TEFAS geçmiş verisi şu anda çekilemiyor.")
else:
    with st.spinner("📡 Geçmiş veriler yükleniyor... (ilk açılışta 30-60 saniye sürebilir)"):
        mf = analyze_money_flow(tefas_full, period_start=mf_start, period_end=mf_end)

    if mf is None:
        st.warning("Para akışı analizi hesaplanamadı.")
    else:
        monthly = mf["monthly_selected"]
        comp = mf["comparison"]
        lt = mf["long_term"]
        seasonal_cal = mf["seasonal_calendar"]
        momentum_df = mf["momentum_selected"]

        # =====================================================================
        # 4-METRİK ÖZET DASHBOARD
        # =====================================================================
        st.markdown("#### 📊 Özet Dashboard")

        # Bu ay akış
        if not monthly.empty:
            last = monthly.iloc[-1]
            curr_flow = float(last["total_net_flow"])
        else:
            curr_flow = 0.0

        # Ivme durumu
        if not momentum_df.empty and not momentum_df["momentum"].dropna().empty:
            last_mom = float(momentum_df["momentum"].dropna().iloc[-1])
            if last_mom > 0:
                mom_status = "✅ Yükseliyor"
            elif last_mom < 0:
                mom_status = "⚠️ Düşüyor"
            else:
                mom_status = "➖ Yatay"
        else:
            mom_status = "N/A"

        # Uzun vade ort
        all_time_avg = lt.get("all_time_avg", 0)

        # Mevsimsel uyum
        seasonal_match = "N/A"
        if not monthly.empty and seasonal_cal:
            today_m = date.today().month
            curr_month = monthly[monthly["year_month"].apply(lambda x: x.month == today_m)]
            entry = next((e for e in seasonal_cal if e["month_num"] == today_m), None)
            if not curr_month.empty and entry and entry["avg_flow"] != 0:
                cf = float(curr_month.iloc[-1]["total_net_flow"])
                ha = entry["avg_flow"]
                if (cf >= 0 and ha >= 0) or (cf <= 0 and ha <= 0):
                    seasonal_match = "✅ Normal"
                else:
                    seasonal_match = "⚠️ Aykırı"

        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.metric("Bu Ay Akış", f"{curr_flow/1e9:+.1f} milyar ₺")
        with d2:
            st.metric("İvme Durumu", mom_status)
        with d3:
            st.metric("Uzun Vade Ort", f"{all_time_avg/1e9:+.1f} milyar ₺/ay")
        with d4:
            st.metric("Mevsimsel Uyum", seasonal_match)

        # =====================================================================
        # AKILLI YORUM
        # =====================================================================
        commentary = mf.get("commentary", "")
        if commentary:
            st.info(f"💬 {commentary}")

        # =====================================================================
        # MEVCUT AY VURGUSU
        # =====================================================================
        curr_highlight = current_month_highlight(seasonal_cal, monthly)
        if curr_highlight:
            with st.expander("📅 Mevcut Ay — Tarihsel Karşılaştırma", expanded=True):
                st.markdown(curr_highlight)

        # =====================================================================
        # EXPORT BUTONU
        # =====================================================================
        export_buffer = export_to_excel(monthly, seasonal_cal, momentum_df)
        st.download_button(
            label="📥 Raporu İndir (Excel)",
            data=export_buffer,
            file_name=f"TLY_Para_Akisi_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # =====================================================================
        # KARŞILAŞTIRMA KARTI
        # =====================================================================
        if comp and lt:
            st.markdown("#### 📊 Uzun Vade Karşılaştırması")
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.metric(
                    "Seçili Dönem Ortalaması",
                    f"{comp['period_avg']/1e9:+.2f} milyar ₺/ay",
                )
            with k2:
                st.metric(
                    "Uzun Vade Ortalaması",
                    f"{comp['all_time_avg']/1e9:+.2f} milyar ₺/ay",
                )
            with k3:
                pct = comp.get("pct_diff")
                st.metric("Fark",
                          f"{pct:+.1f}%" if pct is not None else "N/A")
            with k4:
                zs = comp.get("z_score")
                st.metric("Z-Score", f"{zs:.2f}" if zs is not None else "N/A")
            st.info(f"**Değerlendirme:** {comp['assessment']}")

            with st.expander("📈 Uzun Vade İstatistikler"):
                s1, s2, s3 = st.columns(3)
                with s1:
                    mi = lt.get("max_inflow")
                    st.metric(
                        "En Yüksek Aylık Giriş",
                        f"{mi/1e9:+.2f} milyar ₺" if mi is not None else "-",
                    )
                    st.caption(str(lt.get("max_inflow_month", "")))
                with s2:
                    mo = lt.get("max_outflow")
                    st.metric(
                        "En Yüksek Aylık Çıkış",
                        f"{mo/1e9:+.2f} milyar ₺" if mo is not None else "-",
                    )
                    st.caption(str(lt.get("max_outflow_month", "")))
                with s3:
                    st.metric(
                        "Standart Sapma",
                        f"{lt['all_time_std']/1e9:.2f} milyar ₺",
                    )

        # =====================================================================
        # UYARILAR
        # =====================================================================
        if mf["warnings"]:
            st.markdown("#### 🔔 Uyarılar")
            for w in mf["warnings"]:
                if "🚨" in w:
                    st.error(w)
                elif "⚠️" in w:
                    st.warning(w)
                else:
                    st.info(w)

        # =====================================================================
        # MEVSİMSEL TAKVİM TABLOSU
        # =====================================================================
        if seasonal_cal:
            st.markdown("#### 📅 Mevsimsel Takvim (Tarihsel)")

            def _seasonal_assessment_local(entry):
                if entry["total_years"] == 0:
                    return "➖ Veri yok"
                ratio = entry["positive_years"] / entry["total_years"]
                if ratio >= 0.8:
                    return "✅ Güçlü giriş ayı"
                elif ratio >= 0.6:
                    return "✅ Giriş ayı"
                elif ratio <= 0.2:
                    return "🚨 Tarihsel çıkış ayı"
                elif ratio <= 0.4:
                    return "⚠️ Çıkış eğilimli"
                else:
                    return "➖ Karışık"

            cal_rows = []
            for e in seasonal_cal:
                avg_str = f"{e['avg_flow']/1e9:+.1f} milyar" if e["total_years"] > 0 else "-"
                pos_str = f"{e['positive_years']}/{e['total_years']}" if e["total_years"] > 0 else "-"

                cal_rows.append({
                    "Ay": e["month_name"],
                    "Tarihsel Ort": avg_str,
                    "Pozitif Yıl": pos_str,
                    "Değerlendirme": _seasonal_assessment_local(e),
                    "En İyi Yıl": f"{e['best_year']}" if e.get("best_year") else "-",
                    "En Kötü Yıl": f"{e['worst_year']}" if e.get("worst_year") else "-",
                })

            cal_df = pd.DataFrame(cal_rows)

            # Mevcut ayı vurgulamak için df'e styling
            today_m_idx = date.today().month - 1  # 0-indexed
            def _row_style(row):
                if row.name == today_m_idx:
                    return ["background-color: #1a3a5c; font-weight: bold"] * len(row)
                return [""] * len(row)

            styled = cal_df.style.apply(_row_style, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True)
            st.caption("Mevcut ay mavi vurgulu satırdır.")

        # =====================================================================
        # GRAFİK 1: Aylık Bar Chart
        # =====================================================================
        if not monthly.empty:
            st.markdown("#### 📊 Aylık Net Para Giriş/Çıkışı")
            months = monthly["year_month_str"].tolist()
            flows = (monthly["total_net_flow"] / 1e9).tolist()
            ma = (monthly["flow_ma_12"] / 1e9).tolist()

            bar_colors = ["#27ae60" if f >= 0 else "#e74c3c" for f in flows]
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(
                x=months, y=flows,
                marker_color=bar_colors,
                name="Net Akış",
                hovertemplate="%{x}<br>Net Akış: %{y:+.2f} milyar ₺<extra></extra>",
            ))
            fig1.add_trace(go.Scatter(
                x=months, y=ma,
                mode="lines",
                line=dict(color="#f39c12", width=2),
                name="12 Aylık HA",
            ))

            # Mevsimsel referans çizgileri
            if show_seasonal_ref and seasonal_cal:
                for entry in seasonal_cal:
                    mn = entry["month_name"]
                    avg_flow_b = entry["avg_flow"] / 1e9
                    if entry["total_years"] > 0:
                        matching = [i for i, m in enumerate(months) if m.endswith(f"-{entry['month_num']:02d}")]
                        if matching:
                            fig1.add_trace(go.Scatter(
                                x=[months[matching[0]], months[matching[-1]]],
                                y=[avg_flow_b, avg_flow_b],
                                mode="lines",
                                line=dict(color="#8e44ad", dash="dot", width=1.3),
                                name=f"{mn} ort.",
                                showlegend=False,
                                hovertemplate=f"{mn} tarihsel ort: %{{y:+.2f}} milyar<extra></extra>",
                            ))

            fig1.update_layout(
                xaxis_title="Ay",
                yaxis_title="milyar TL",
                hovermode="x unified",
                height=450,
                margin=dict(l=20, r=20, t=10, b=20),
            )
            st.plotly_chart(fig1, use_container_width=True)

        # =====================================================================
        # GRAFİK 2: AUM ve Akış Karşılaştırması
        # =====================================================================
        if not monthly.empty:
            st.markdown("#### 📈 AUM ve Net Akış Karşılaştırması")
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])

            fig2.add_trace(go.Scatter(
                x=months,
                y=(monthly["aum_end"] / 1e9).tolist(),
                mode="lines+markers",
                line=dict(color="#2980b9", width=2),
                name="AUM",
            ), secondary_y=False)

            fig2.add_trace(go.Bar(
                x=months, y=flows,
                marker_color=bar_colors,
                name="Net Akış",
                opacity=0.5,
            ), secondary_y=True)

            fig2.update_layout(
                height=450,
                margin=dict(l=20, r=20, t=10, b=20),
                hovermode="x unified",
            )
            fig2.update_yaxes(title_text="AUM (milyar ₺)", secondary_y=False)
            fig2.update_yaxes(title_text="Net Akış (milyar ₺)", secondary_y=True)
            st.plotly_chart(fig2, use_container_width=True)

        # =====================================================================
        # GRAFİK 3: Haftalık İvme
        # =====================================================================
        if not momentum_df.empty:
            st.markdown("#### ⚡ Haftalık İvme")
            mom_weeks = momentum_df["year_week"].tolist()
            mom_vals = (momentum_df["momentum"] / 1e9).tolist()
            mom_colors = [
                "#27ae60" if v >= 0 else "#e74c3c" for v in mom_vals
            ]

            fig3 = go.Figure()
            fig3.add_hline(
                y=0, line_dash="dash", line_color="#95a5a6", opacity=0.5,
            )
            fig3.add_trace(go.Scatter(
                x=mom_weeks, y=mom_vals,
                mode="markers+lines",
                marker=dict(color=mom_colors, size=7),
                line=dict(color="#bdc3c7", width=0.8),
                name="İvme",
                hovertemplate="%{x}<br>İvme: %{y:+.3f} milyar ₺/gün<extra></extra>",
            ))
            fig3.update_layout(
                xaxis_title="Hafta",
                yaxis_title="İvme (milyar TL/gün)",
                height=400,
                margin=dict(l=20, r=20, t=10, b=20),
            )
            st.plotly_chart(fig3, use_container_width=True)

        # =====================================================================
        # AYLIK AKIŞ TABLOSU
        # =====================================================================
        if not monthly.empty:
            st.markdown("#### 📋 Aylık Akış Listesi")
            table_df = monthly[[
                "year_month_str", "total_net_flow",
                "aum_change_pct", "investor_change",
            ]].copy()
            table_df.columns = [
                "Ay", "Net Akış (TL)", "AUM Değişimi (%)", "Yatırımcı Değişimi",
            ]

            def _flow_label(v):
                if pd.isna(v):
                    return "-"
                return f"{v/1e9:+.2f} milyar ₺"

            def _pct_label(v):
                if pd.isna(v):
                    return "-"
                return f"{v:+.2f}%"

            def _inv_label(v):
                if pd.isna(v):
                    return "-"
                return f"{v:+.0f}"

            table_df["Net Akış (TL)"] = table_df["Net Akış (TL)"].apply(_flow_label)
            table_df["AUM Değişimi (%)"] = table_df["AUM Değişimi (%)"].apply(_pct_label)
            table_df["Yatırımcı Değişimi"] = table_df["Yatırımcı Değişimi"].apply(_inv_label)

            def _degerlendir(row):
                try:
                    fs = str(row["Net Akış (TL)"])
                    if "milyar" in fs:
                        val = float(fs.split()[0])
                        if val > 0.1:
                            return "✅ Giriş"
                        elif val < -0.1:
                            return "🔴 Çıkış"
                except Exception:
                    pass
                return "➖ Yatay"

            table_df["Değerlendirme"] = table_df.apply(_degerlendir, axis=1)
            table_df = table_df.iloc[::-1].reset_index(drop=True)

            st.dataframe(
                table_df,
                use_container_width=True,
                hide_index=True,
            )

# ---------------------------------------------------------------------------
# Alt bilgi
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"TLY Risk Analiz Aracı v1.0  ·  Veri: Yahoo Finance (~15 dk gecikmeli)  ·  "
    f"Son yenileme: {datetime.now().strftime('%H:%M:%S')}  ·  "
    "config.py'yi aylık güncelleyin."
)