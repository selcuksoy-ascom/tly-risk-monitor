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
import pandas as pd
from datetime import date, datetime
from config import (
    PORTFOLIO, EQUITY_RATIO, DEFAULT_CAPITAL, PANIC_RATE,
    GROUP_TICKERS, CORRELATION_THRESHOLD, HISTORY_DAYS,
)
from data_fetcher import fetch_all_portfolio_data
from risk_analyzer import analyze_portfolio
from simulator import run_simulation

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
    .critical-row { background: #fce8e6 !important; }
    .rotation-row { background: #e8f5e9 !important; }
    .warning-row  { background: #fef7e0 !important; }
    hr { margin: 0.5rem 0; }
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

rows = []
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

    price_str = f"{price:,.4f}" if price is not None else "—"
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else "—"
    vol_str = f"%{vol_ratio:.0f}" if vol_ratio is not None else "—"

    # Durum emojisi
    if is_critical:
        status_icon = "🔴"
    elif is_rotation:
        status_icon = "🔵"
    elif data.get("error"):
        status_icon = "⚫"
    else:
        status_icon = "🟢"

    rows.append({
        "Hisse": short,
        "Ad": name,
        "Ağırlık": f"%{weight:.2f}",
        "Fiyat (₺)": price_str,
        "Değişim": change_str,
        "Hacim/Ort": vol_str,
        "Durum": f"{status_icon} {liq_status}",
        "_critical": is_critical,
        "_rotation": is_rotation,
        "_change": change_pct or 0,
        "_error": data.get("error", False),
    })

df = pd.DataFrame(rows)


def highlight_rows(row):
    if row["_critical"]:
        return ["background-color: #fce8e6"] * len(row)
    if row["_rotation"]:
        return ["background-color: #e8f5e9"] * len(row)
    if row["_error"]:
        return ["background-color: #f1f3f4"] * len(row)
    if row["_change"] < 0:
        return ["background-color: #fef7e0"] * len(row)
    return [""] * len(row)


display_cols = ["Hisse", "Ad", "Ağırlık", "Fiyat (₺)", "Değişim", "Hacim/Ort", "Durum"]
styled = df[display_cols].style.apply(highlight_rows, axis=1)

st.dataframe(styled, use_container_width=True, hide_index=True, height=(len(rows) + 1) * 38)

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
        st.progress(min(corr / 1.0, 1.0), text=f"Korelasyon: {corr:.2f}")
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

if not critical_alerts and not rotation_logs:
    st.success("✅ Bugün için kritik uyarı yok.")
else:
    for alert in critical_alerts:
        st.error(f"🔴 {alert}")
    for log in rotation_logs:
        st.info(f"🔵 {log}")

# ---------------------------------------------------------------------------
# Alt bilgi
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"TLY Risk Analiz Aracı v1.0  ·  Veri: Yahoo Finance (~15 dk gecikmeli)  ·  "
    f"Son yenileme: {datetime.now().strftime('%H:%M:%S')}  ·  "
    "config.py'yi aylık güncelleyin."
)