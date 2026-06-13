# =============================================================================
# main_android.py — TLY Mobil (Kivy) Ana Uygulaması
# =============================================================================
# Android cihazda Kivy framework ile arayüz sunar.
# Pydroid3:   doğrudan "python main_android.py"  ile çalıştır.
# APK üretimi: buildozer android debug           ile paketle.
# =============================================================================
#
# Modüller (yeniden kullanılan):
#   config.py         → portföy tanımları
#   data_fetcher.py   → yfinance verisi
#   risk_analyzer.py  → 3‑kural motoru
#   simulator.py      → T+2 valör hesabı
# =============================================================================

import sys, os, threading
from datetime import date

# ---------------------------------------------------------------------------
# Kivy config – performans ve uyumluluk
# ---------------------------------------------------------------------------
from kivy.config import Config
Config.set("graphics", "window_state", "maximized")        # tam ekran
Config.set("kivy", "exit_on_escape", "0")                  # geri tuşu çıkmasın

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.uix.progressbar import ProgressBar
from kivy.core.window import Window

# ---------------------------------------------------------------------------
# Arka plan renkleri ve metin stilleri
# ---------------------------------------------------------------------------
BG_DARK  = (0.02,  0.06,  0.08,  1)     # koyu lacivert‑siyah
CARD     = (0.08,  0.15,  0.18,  1)     # kart / panel
RED_BG   = (0.65,  0.05,  0.05,  1)
YELLOW_BG = (0.55, 0.45,  0.0,   1)
GREEN_BG = (0.05,  0.55,  0.15,  1)
CYAN_BG  = (0.05,  0.35,  0.45,  1)
WHITE    = (0.95,  0.95,  0.95,  1)
GRAY     = (0.55,  0.55,  0.55,  1)
RED_TXT  = (1,    0.3,   0.3,   1)
YELLOW_TXT = (1,  0.85,  0.1,   1)
GREEN_TXT = (0.3, 1,    0.3,   1)
CYAN_TXT = (0.3,  0.9,  0.9,   1)

Window.clearcolor = BG_DARK


# ---------------------------------------------------------------------------
# Yeniden kullanılabilir yardımcı widget
# ---------------------------------------------------------------------------
class Card(BoxLayout):
    """Yuvarlak kenarlı, koyu arkaplanlı bilgi kartı."""
    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, **kw)


class H1(Label):
    def __init__(self, text="", **kw):
        super().__init__(text=text, font_size="20sp", bold=True,
                         color=WHITE, size_hint_y=None, height=40, **kw)


class H2(Label):
    def __init__(self, text="", **kw):
        super().__init__(text=text, font_size="16sp", bold=True,
                         color=CYAN_TXT, size_hint_y=None, height=32, **kw)


class Body(Label):
    def __init__(self, text="", **kw):
        super().__init__(text=text, font_size="13sp", color=GRAY,
                         size_hint_y=None, height=22, halign="left",
                         valign="top", **kw)
        self.bind(size=self._update_padding)

    def _update_padding(self, *_):
        self.text_size = (self.width - 20, None)


# ---------------------------------------------------------------------------
# Ana Ekran
# ---------------------------------------------------------------------------
class MainScreen(ScrollView):
    """Tam ekran kaydırılabilir rapor görünümü."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.do_scroll_x = False

        # layout
        self.root_box = BoxLayout(orientation="vertical",
                                  size_hint_y=None, padding=12, spacing=8)
        self.root_box.bind(minimum_height=self.root_box.setter("height"))
        self.add_widget(self.root_box)

        # ── BAŞLIK ──
        self.root_box.add_widget(H1("TLY RİSK RAPORU"))
        date_lbl = Label(text=date.today().strftime("%d %B %Y"),
                         font_size="13sp", color=GRAY, size_hint_y=None, height=22)
        self.root_box.add_widget(date_lbl)

        # ── KONTROL DÜĞMELERİ ──
        self.capital_input = TextInput(
            text="500000", multiline=False, input_filter="int",
            font_size="15sp", halign="center",
            foreground_color=WHITE,
            background_color=(0.1,0.2,0.25,1),
            cursor_color=WHITE, size_hint=(1, None), height=44)

        btn_box = BoxLayout(orientation="horizontal",
                            size_hint_y=None, height=50, spacing=8)

        self.run_btn = Button(text="ANALİZİ BAŞLAT",
                              font_size="15sp", bold=True,
                              background_normal="",
                              background_color=(0.1, 0.5, 0.8, 1),
                              color=WHITE, size_hint=(1, None), height=50)
        self.run_btn.bind(on_press=self.start_analysis)

        btn_box.add_widget(self.run_btn)
        self.root_box.add_widget(Label(text="Anapara (TL):", font_size="12sp",
                                       color=GRAY, size_hint_y=None, height=18))
        self.root_box.add_widget(self.capital_input)
        self.root_box.add_widget(btn_box)

        # ── YÜKLENİYOR ÇUBUĞU ──
        self.progress = ProgressBar(max=100, value=0,
                                    size_hint_y=None, height=6)
        self.progress_box = BoxLayout(size_hint_y=None, height=6)
        self.progress_box.add_widget(self.progress)
        self.root_box.add_widget(self.progress_box)

        # ── RAPOR ALANI (dinamik doldurulacak) ──
        self.report_area = None

    # ------------------------------------------------------------------
    def start_analysis(self, *_):
        """Thread içinde analiz yap, UI bloklanmasın."""
        self.run_btn.disabled = True
        self.run_btn.text = "ÇEKİLİYOR..."
        self.run_btn.background_color = (0.3, 0.3, 0.3, 1)
        threading.Thread(target=self._do_analysis, daemon=True).start()

    def _do_analysis(self):
        """Arka planda ağır iş (yfinance + analiz)."""
        try:
            cap = int(self.capital_input.text or "500000")
        except ValueError:
            cap = 500000

        # import'lar arka planda
        from config import PORTFOLIO, EQUITY_RATIO, PANIC_RATE
        from data_fetcher import fetch_all_portfolio_data
        from risk_analyzer import analyze_portfolio
        from simulator import run_simulation

        # ilerleme bildirimi
        Clock.schedule_once(lambda dt: self._set_progress(0.1), 0)

        portfolio_data = fetch_all_portfolio_data(PORTFOLIO)
        Clock.schedule_once(lambda dt: self._set_progress(0.5), 0)

        analysis = analyze_portfolio(portfolio_data)
        Clock.schedule_once(lambda dt: self._set_progress(0.75), 0)

        sim = run_simulation(capital=cap, equity_ratio=EQUITY_RATIO,
                             panic_rate=PANIC_RATE)
        Clock.schedule_once(lambda dt: self._set_progress(1.0), 0)

        Clock.schedule_once(
            lambda dt: self._render_report(portfolio_data, analysis, sim), 0)

    def _set_progress(self, val):
        self.progress.value = int(val * 100)

    # ------------------------------------------------------------------
    def _render_report(self, pdata, analysis, sim):
        """Kivy widget'ları ile raporu ekrana çiz."""
        # Eski raporu temizle
        if self.report_area:
            self.root_box.remove_widget(self.report_area)

        area = BoxLayout(orientation="vertical",
                         size_hint_y=None, spacing=10)
        area.bind(minimum_height=area.setter("height"))

        # ─── RİSK TABLOSU ───
        area.add_widget(H2("Risk Tablosu"))
        for ticker, d in analysis["per_stock"].items():
            short = ticker.replace(".IS", "")

            row = BoxLayout(orientation="vertical",
                            size_hint_y=None, height=70, padding=[6,4], spacing=2)
            with row.canvas.before:
                from kivy.graphics import Color, RoundedRectangle
                bg_color = CARD
                if d.get("is_critical"):
                    bg_color = RED_BG
                elif d.get("is_rotation"):
                    bg_color = CYAN_BG
                Color(*bg_color)
                RoundedRectangle(size=row.size, pos=row.pos, radius=[8])
            row.bind(size=lambda w,s: w.canvas.before.clear() or
                     (setattr(Color(*bg_color), "rgba", bg_color),
                      RoundedRectangle(size=w.size, pos=w.pos, radius=[8])))

            name = d.get("name","?")[:22]
            w = d.get("weight", 0)
            p = d.get("price")
            ch = d.get("change_pct")
            vr = d.get("volume_ratio")
            st = d.get("liquidity_status","?")

            price_str = f"{p:.4f}" if p else "N/A"
            ch_str = f"%{ch:+.2f}" if ch is not None else "N/A"
            vr_str = f"Hacim/Ort: %{vr:.0f}" if vr else "H/O: N/A"

            t1 = Label(text=f"[b]{short}[/b]  {name}   [b]%{w:.2f}[/b]",
                       font_size="12sp", markup=True, color=WHITE,
                       size_hint_y=None, height=20)
            t2 = Label(text=f"{price_str} ₺   {ch_str}   {vr_str}",
                       font_size="11sp", color=GRAY, size_hint_y=None, height=18)
            t3 = Label(text=f"Durum: {st}", font_size="11sp",
                       color=RED_TXT if d.get("is_critical") else
                             CYAN_TXT if d.get("is_rotation") else GREEN_TXT,
                       size_hint_y=None, height=18)
            row.add_widget(t1)
            row.add_widget(t2)
            row.add_widget(t3)
            area.add_widget(row)

        # ─── SİSTEMİK RİSK ───
        area.add_widget(H2("Sistemik Risk"))
        s = analysis["systemic"]
        corr = s.get("correlation")
        tickers = "/".join(t.replace(".IS","") for t in s.get("tickers",[]))
        if corr is not None:
            corr_color = RED_TXT if s.get("is_critical") else YELLOW_TXT if corr>0.8 else GREEN_TXT
            txt = f"Grup Korelasyonu ({tickers}):  [b]{corr:.2f}[/b]"
        else:
            txt = f"Grup Korelasyonu ({tickers}):  Hesaplanamadı"
            corr_color = GRAY
        area.add_widget(Label(text=txt, font_size="13sp", markup=True,
                              color=corr_color, size_hint_y=None, height=24))

        # ─── T+2 SİMÜLASYON ───
        area.add_widget(H2("T+2 Valör Simülatörü"))
        evals = sim["daily_equity_values"]
        loss_tl = sim["equity_loss_tl"]
        loss_pct = sim["equity_loss_pct"]
        remaining = sim["remaining_portfolio"]
        cap = sim["capital"]

        def tl(v): return f"{v:,.0f} ₺".replace(",",".")

        sim_lines = [
            f"Anapara:            {tl(cap)}",
            f"Hisse Port. (Gün0): {tl(evals[0])}",
        ]
        for i in range(1, len(evals)):
            sim_lines.append(f"Gün {i} (T+{i}):       {tl(evals[i])}   (-%{sim['panic_rate']:.0f}/gün)")
        sim_lines.append("")
        sim_lines.append(f"Toplam Hisse Kaybı:  {tl(loss_tl)}   (%{loss_pct:.1f})")
        sim_lines.append(f"Kalan Portföy:       {tl(remaining)}")

        for line in sim_lines:
            clr = RED_TXT if "Kayıp" in line else YELLOW_TXT if "Kalan" in line else GRAY
            area.add_widget(Label(text=line, font_size="12sp", color=clr,
                                  size_hint_y=None, height=22))

        # ─── KRİTİK UYARILAR ───
        area.add_widget(H2("Kritik Uyarılar"))
        alerts = analysis.get("critical_alerts", [])
        rotations = analysis.get("rotation_logs", [])
        if not alerts and not rotations:
            area.add_widget(Label(text="✓ Uyarı yok", font_size="13sp",
                                  color=GREEN_TXT, size_hint_y=None, height=24))
        for a in alerts:
            area.add_widget(Label(text=f"⚠ {a}", font_size="12sp",
                                  color=RED_TXT, size_hint_y=None, height=24))
        for r in rotations:
            area.add_widget(Label(text=f"↩ {r}", font_size="12sp",
                                  color=CYAN_TXT, size_hint_y=None, height=24))

        # ─── BAĞLANTI ───
        area.add_widget(Label(text="", size_hint_y=None, height=10))  # spacer

        self.report_area = area
        self.root_box.add_widget(area)

        # butonu geri aç
        self.run_btn.text = "YENİDEN ÇALIŞTIR"
        self.run_btn.background_color = (0.1, 0.5, 0.8, 1)
        self.run_btn.disabled = False
        self._set_progress(0.0)


# ---------------------------------------------------------------------------
# Kivy App sınıfı
# ---------------------------------------------------------------------------
class TLYApp(App):
    def build(self):
        self.title = "TLY Risk"
        return MainScreen()


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Android'de buildozer -> .apk yolunda app çalışır.
    # Pydroid3'te bu script doğrudan çalıştırılabilir.
    TLYApp().run()