# =============================================================================
# data_fetcher.py - Piyasa Verisi Çekme Modülü
# =============================================================================
# yfinance kullanarak hisse senedi verilerini çeker.
# Hata durumunda None döndürür, programı çökertmez.
# =============================================================================

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


def fetch_stock_data(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Belirtilen hisse için anlık piyasa verisini çeker.

    Returns:
        dict: {
            'ticker': str,
            'price': float,
            'change_pct': float,   # günlük değişim %
            'volume': int,
        }
        None: Veri çekilemezse
    """
    try:
        stock = yf.Ticker(ticker)

        # Bugün ve dün için veri çek (en az 2 gün gerekli)
        end = datetime.now()
        start = end - timedelta(days=5)  # Hafta sonu/tatil için 5 gün buffer

        hist = stock.history(start=start.strftime("%Y-%m-%d"),
                             end=end.strftime("%Y-%m-%d"),
                             auto_adjust=True)

        if hist.empty or len(hist) < 1:
            print(f"  [UYARI] {ticker}: Güncel veri bulunamadı.")
            return None

        # Son kapanış
        last_row = hist.iloc[-1]
        current_price = float(last_row["Close"])
        current_volume = int(last_row["Volume"])

        # Günlük değişim %
        if len(hist) >= 2:
            prev_close = float(hist.iloc[-2]["Close"])
            if prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100.0
            else:
                change_pct = 0.0
        else:
            # Sadece bir gün verisi varsa open/close farkından hesapla
            open_price = float(last_row["Open"])
            if open_price > 0:
                change_pct = ((current_price - open_price) / open_price) * 100.0
            else:
                change_pct = 0.0

        return {
            "ticker": ticker,
            "price": round(current_price, 4),
            "change_pct": round(change_pct, 2),
            "volume": current_volume,
        }

    except Exception as e:
        print(f"  [HATA] {ticker} verisi çekilemedi: {e}")
        return None


def fetch_history(ticker: str, days: int = 30) -> Optional[pd.DataFrame]:
    """
    Belirtilen hisse için son N günlük geçmiş veriyi çeker.

    Returns:
        pd.DataFrame: Open, High, Low, Close, Volume sütunları
        None: Veri çekilemezse
    """
    try:
        stock = yf.Ticker(ticker)
        end = datetime.now()
        # Buffer ekle (hafta sonu / tatil günleri için)
        start = end - timedelta(days=days + 15)

        hist = stock.history(start=start.strftime("%Y-%m-%d"),
                             end=end.strftime("%Y-%m-%d"),
                             auto_adjust=True)

        if hist.empty:
            print(f"  [UYARI] {ticker}: Geçmiş veri bulunamadı.")
            return None

        # Son N işlem gününü al
        hist = hist.tail(days)

        if len(hist) < 5:
            print(f"  [UYARI] {ticker}: Yeterli geçmiş veri yok ({len(hist)} gün).")
            return None

        return hist

    except Exception as e:
        print(f"  [HATA] {ticker} geçmiş verisi çekilemedi: {e}")
        return None


def get_avg_volume(ticker: str, days: int = 30) -> Optional[float]:
    """
    Belirtilen hisse için son N günlük ortalama işlem hacmini hesaplar.

    Returns:
        float: Ortalama günlük işlem hacmi
        None: Veri yoksa
    """
    hist = fetch_history(ticker, days)

    if hist is None:
        return None

    if "Volume" not in hist.columns:
        print(f"  [UYARI] {ticker}: Hacim verisi yok.")
        return None

    # Sıfır hacimli günleri filtrele (işlem olmayan günler)
    volumes = hist["Volume"].replace(0, pd.NA).dropna()

    if len(volumes) == 0:
        return None

    avg_vol = float(volumes.mean())
    return round(avg_vol, 0)


def fetch_all_portfolio_data(portfolio: dict) -> Dict[str, Dict[str, Any]]:
    """
    Portföydeki tüm hisseler için veri çeker.

    Args:
        portfolio: config.PORTFOLIO dict

    Returns:
        dict: {ticker: {price, change_pct, volume, avg_volume, history, error}}
    """
    results = {}

    print("\n  Piyasa verisi çekiliyor...")

    for ticker, info in portfolio.items():
        print(f"  → {ticker} ({info['name']})...", end=" ", flush=True)

        stock_data = fetch_stock_data(ticker)
        avg_vol = get_avg_volume(ticker, days=30)
        history = fetch_history(ticker, days=30)

        if stock_data is not None:
            results[ticker] = {
                **stock_data,
                "avg_volume": avg_vol,
                "history": history,
                "weight": info["weight"],
                "prev_weight": info.get("prev_weight", info["weight"]),
                "name": info["name"],
                "category": info["category"],
                "error": False,
            }
            print("OK")
        else:
            results[ticker] = {
                "ticker": ticker,
                "price": None,
                "change_pct": None,
                "volume": None,
                "avg_volume": avg_vol,
                "history": history,
                "weight": info["weight"],
                "prev_weight": info.get("prev_weight", info["weight"]),
                "name": info["name"],
                "category": info["category"],
                "error": True,
            }
            print("HATA")

    return results
