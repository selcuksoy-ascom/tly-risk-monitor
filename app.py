# =============================================================================
# app.py — TLY Risk Analiz Aracı (Streamlit Web Arayüzü)
# =============================================================================
# Çalıştır: streamlit run app.py
# Tarayıcıda http://localhost:8501 adresinde açılır.
# =============================================================================

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from datetime import date, datetime
from config import (
    PORTFOLIO, EQUITY_RATIO, DEFAULT_CAPITAL, PANIC_RATE,
    GROUP_TICKERS, CORRELATION_THRESHOLD,
)
from data_fetcher import fetch_all_portfolio_data
from risk_analyzer import analyze_portfolio
from simulator import run_simulation
from tefas_fetcher import analyze_fund_health

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
# Alt bilgi
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"TLY Risk Analiz Aracı v1.0  ·  Veri: Yahoo Finance (~15 dk gecikmeli)  ·  "
    f"Son yenileme: {datetime.now().strftime('%H:%M:%S')}  ·  "
    "config.py'yi aylık güncelleyin."
)