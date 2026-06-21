# =============================================================================
# stress_test.py - Fonoloji Holdings Tabanlı Stress Testi
# =============================================================================
# Fonoloji /holdings endpoint'inden TLY fonunun güncel varlık dağılımını çeker,
# repo / hisse / fon / tahvil ağırlıklarını hesaplar ve BIST çöküş senaryosuna
# karşı portföy dayanıklılığını ölçer.
#
# DÜZELTME: Fonoloji "items" listesinde sadece en güncel ayı, "previousItems"
# veya "holdings" altında ise TÜM geçmiş ayları döndürür. Bu script SADECE
# report_date == latestPeriod olan kayıtları dikkate alır.
# =============================================================================

import os
import sys
import json
from datetime import date
from typing import Optional, Dict, Any, List, Tuple

import requests

# ---------------------------------------------------------------------------
# Fonoloji API yapılandırması
# ---------------------------------------------------------------------------
FONOLOJI_BASE_URL = os.environ.get(
    "FONOLOJI_BASE_URL",
    "https://api.fonoloji.com",  # <-- kendi endpoint'in ile değiştir
)
FONOLOJI_API_KEY = os.environ.get("FONOLOJI_API_KEY", "")
FONOLOJI_FUND_CODE = os.environ.get("FONOLOJI_FUND_CODE", "TLY")

# ---------------------------------------------------------------------------
# Stress test parametreleri
# ---------------------------------------------------------------------------
BIST_CRASH_SCENARIOS = [10, 20, 30, 40, 50]  # % düşüş senaryoları
BOND_HAIRCUT = 5.0          # tahvil / sukuk şokta %5 değer kaybı
REPO_ASSUMED_SAFE = True    # repo neredeyse nakittir, kayıp = 0
FUND_HAIRCUT = 15.0         # diğer fonlarda BIST'in ~yarısı kadar kayıp

# Hata toleransı — varlık toplamı bu aralıktaysa sorun yok
ALLOCATION_TOLERANCE = 2.0  # ±%2


# =============================================================================
# API İletişimi
# =============================================================================

def _fetch_holdings_raw() -> Optional[Dict[str, Any]]:
    """Fonoloji /holdings endpoint'inden ham JSON döndürür."""
    url = f"{FONOLOJI_BASE_URL}/holdings"
    headers = {"Authorization": f"Bearer {FONOLOJI_API_KEY}"}
    params = {"fund_code": FONOLOJI_FUND_CODE}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data
    except requests.RequestException as e:
        print(f"[HATA] Fonoloji API çağrısı başarısız: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[HATA] JSON parse hatası: {e}")
        return None


# =============================================================================
# Veri Ayrıştırma (düzeltilmiş haliyle)
# =============================================================================

def _extract_latest_period(raw: Dict[str, Any]) -> Optional[str]:
    """Fonoloji yanıtından latestPeriod alanını okur (örn: '2026-05')."""
    period = raw.get("latestPeriod")
    if period:
        return str(period)
    # Fallback: data.latestPeriod
    data = raw.get("data", {})
    if isinstance(data, dict):
        period = data.get("latestPeriod")
        if period:
            return str(period)
    return None


def _get_all_items(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fonoloji yanıtından TÜM holding kayıtlarını toplar.

    Fonoloji yapısı:
      - "items"        : yalnızca en güncel ay
      - "previousItems" veya "holdings" : geçmiş aylar dahil tüm veri
      - "data.items" / "data.holdings"  : alternatif konumlar

    Bu fonksiyon olası tüm konumlardaki kayıtları birleştirir.
    """
    all_records: List[Dict[str, Any]] = []

    # Ana seviye
    for key in ("items", "holdings", "previousItems"):
        records = raw.get(key)
        if isinstance(records, list):
            all_records.extend(records)

    # data altında
    data = raw.get("data")
    if isinstance(data, dict):
        for key in ("items", "holdings", "previousItems"):
            records = data.get(key)
            if isinstance(records, list):
                all_records.extend(records)

    # Tek bir kayıt bile yoksa, tüm JSON'u olduğu gibi yazdır (debug)
    if not all_records:
        print("[UYARI] Hiçbir holding kaydı bulunamadı. Ham yanıt:")
        print(json.dumps(raw, indent=2, ensure_ascii=False, default=str)[:2000])

    return all_records


def _filter_latest_period(
    records: List[Dict[str, Any]],
    latest_period: str,
) -> List[Dict[str, Any]]:
    """
    SADECE report_date == latestPeriod olan kayıtları döndürür.

    DÜZELTME: Bu filtre olmadan, tüm ayların repo/hisse/fon/tahvil
    verileri birbirine karışıp toplam %100'ü aşıyordu.
    """
    filtered = []
    for r in records:
        rd = r.get("report_date") or r.get("reportDate") or r.get("date") or r.get("period")
        if rd is None:
            continue
        if str(rd) == str(latest_period):
            filtered.append(r)
    return filtered


# =============================================================================
# Varlık Sınıflandırma
# =============================================================================

# Her enstrüman tipi için Fonoloji'deki olası anahtar kelimeler
ASSET_KEYWORDS = {
    "repo":   ["repo", "ters repo", "reverse repo", "takasbank", "para piyasası",
               "money market"],
    "stock":  ["hisse", "pay", "stock", "equity", "ortaklık"],
    "fund":   ["fon", "fund", "etf", "gyf", "girişim", "katılma"],
    "bond":   ["tahvil", "bono", "bond", "sukuk", "kira sertifikası",
               "eurobond", "finansman bonosu", "özel sektör", "devlet",
               "private bond", "government"],
}


def _classify_asset(name: str, asset_type: str = "") -> str:
    """
    Enstrüman adına ve tipine bakarak varlık sınıfını belirler.

    Returns: 'repo', 'stock', 'fund', 'bond', 'other'
    """
    text = f"{name} {asset_type}".lower()

    # Repo en hızlı dönen araçtır, önce kontrol et
    for kw in ASSET_KEYWORDS["repo"]:
        if kw in text:
            return "repo"

    for kw in ASSET_KEYWORDS["stock"]:
        if kw in text:
            return "stock"

    for kw in ASSET_KEYWORDS["fund"]:
        if kw in text:
            return "fund"

    for kw in ASSET_KEYWORDS["bond"]:
        if kw in text:
            return "bond"

    return "other"


# =============================================================================
# Ağırlık Hesaplama
# =============================================================================

def _find_value(item: Dict[str, Any]) -> float:
    """Kayıttan ağırlık veya değer alanını bulur, TL'ye çevirir."""
    for key in ("weight", "ratio", "percentage", "value", "amount",
                "portfolioWeight", "portfolioValue", "marketValue"):
        val = item.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0


def calculate_allocation(
    raw: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Varlık dağılımını hesaplar (SADECE en güncel ayın verisiyle).

    Returns:
        {
            'latest_period': str,
            'total_records': int,         # filtresiz toplam kayıt
            'filtered_records': int,      # filtre sonrası kayıt
            'repo_pct': float,
            'stock_pct': float,
            'fund_pct': float,
            'bond_pct': float,
            'other_pct': float,
            'total_pct': float,
            'items': [...],               # sınıflanmış kayıt listesi
        }
        veya None (veri çekilemezse)
    """
    # 1. latestPeriod oku
    latest_period = _extract_latest_period(raw)
    if latest_period is None:
        print("[HATA] latestPeriod bulunamadı. Ham yanıt:")
        print(json.dumps(raw, indent=2, ensure_ascii=False, default=str)[:2000])
        return None

    print(f"\n  latestPeriod      = {latest_period}")

    # 2. Tüm kayıtları topla
    all_records = _get_all_items(raw)
    total_records = len(all_records)
    print(f"  Toplam kayıt (ham) = {total_records}")

    # 3. DÜZELTME: SADECE latestPeriod'a ait kayıtları al
    filtered = _filter_latest_period(all_records, latest_period)
    filtered_count = len(filtered)
    print(f"  Filtre sonrası     = {filtered_count}")
    print(f"  Elenen kayıt       = {total_records - filtered_count}")

    if filtered_count == 0:
        print("[HATA] latestPeriod'a ait hiç kayıt yok!")
        return None

    # 4. Varlık sınıflarına göre topla
    buckets = {"repo": 0.0, "stock": 0.0, "fund": 0.0, "bond": 0.0, "other": 0.0}
    classified_items: List[Dict[str, Any]] = []

    for item in filtered:
        name = str(item.get("name") or item.get("assetName") or item.get("description") or "")
        asset_type = str(item.get("type") or item.get("assetType") or item.get("kind") or "")
        klass = _classify_asset(name, asset_type)
        val = _find_value(item)

        buckets[klass] += val
        classified_items.append({
            "name": name,
            "type": asset_type,
            "class": klass,
            "value": val,
            "report_date": item.get("report_date") or item.get("reportDate") or latest_period,
        })

    # 5. Yüzdelere çevir
    total = sum(buckets.values())
    if total <= 0:
        print("[HATA] Toplam varlık değeri 0 veya negatif.")
        return None

    allocation = {
        "latest_period": latest_period,
        "total_records": total_records,
        "filtered_records": filtered_count,
        "repo_pct": round((buckets["repo"] / total) * 100.0, 2),
        "stock_pct": round((buckets["stock"] / total) * 100.0, 2),
        "fund_pct": round((buckets["fund"] / total) * 100.0, 2),
        "bond_pct": round((buckets["bond"] / total) * 100.0, 2),
        "other_pct": round((buckets["other"] / total) * 100.0, 2),
        "total_pct": 0.0,  # aşağıda hesapla
        "items": classified_items,
    }

    allocation["total_pct"] = round(
        allocation["repo_pct"]
        + allocation["stock_pct"]
        + allocation["fund_pct"]
        + allocation["bond_pct"]
        + allocation["other_pct"],
        2,
    )

    return allocation


# =============================================================================
# Debug Print
# =============================================================================

def print_allocation_debug(alloc: Dict[str, Any]) -> None:
    """Varlık dağılımını konsola detaylı yazdırır."""
    print()
    print("=" * 56)
    print("  FONOLOJİ VARLIK DAĞILIMI (DEBUG)")
    print("=" * 56)
    print(f"  Dönem              : {alloc['latest_period']}")
    print(f"  Ham kayıt sayısı   : {alloc['total_records']}")
    print(f"  Filtreli kayıt     : {alloc['filtered_records']}")
    print(f"  ───────────────────────────────────────")
    print(f"  Repo               : %{alloc['repo_pct']:.2f}")
    print(f"  Hisse Senedi       : %{alloc['stock_pct']:.2f}")
    print(f"  Fon (diğer)        : %{alloc['fund_pct']:.2f}")
    print(f"  Tahvil / Bono      : %{alloc['bond_pct']:.2f}")
    print(f"  Diğer              : %{alloc['other_pct']:.2f}")
    print(f"  ───────────────────────────────────────")
    print(f"  TOPLAM             : %{alloc['total_pct']:.2f}")
    print()

    # Her kalemin detayını göster
    if alloc["items"]:
        print("  Kalem bazında döküm:")
        print(f"  {'Sınıf':<8} {'Değer':>12}  {'Ad':<40}")
        print(f"  {'─'*8} {'─'*12}  {'─'*40}")
        for item in sorted(alloc["items"], key=lambda x: x["value"], reverse=True):
            print(
                f"  {item['class']:<8} "
                f"%{item['value']:>6.2f}      "
                f"{item['name'][:40]}"
            )
        print()


def _validate_total(alloc: Dict[str, Any]) -> None:
    """Toplamın %100 ± tolerans içinde olup olmadığını kontrol eder."""
    total = alloc["total_pct"]
    diff = abs(total - 100.0)

    if diff <= ALLOCATION_TOLERANCE:
        print(f"  ✓  Varlık dağılımı toplamı %{total:.2f} — beklendiği gibi.")
    else:
        print(
            f"  ⚠️  UYARI: Varlık dağılımı toplamı %{total:.2f}, "
            f"beklenenden %{diff:.1f} sapıyor. Veri tutarsızlığı olabilir."
        )


# =============================================================================
# Stress Test Simülasyonu
# =============================================================================

def run_stress_test(
    alloc: Dict[str, Any],
    capital: float = 500_000.0,
) -> List[Dict[str, Any]]:
    """
    BIST çöküş senaryolarına karşı portföy kaybını hesaplar.

    Args:
        alloc: calculate_allocation() çıktısı
        capital: toplam portföy değeri (TL)

    Returns:
        Her senaryo için kayıp tablosu
    """
    stock_pct = alloc["stock_pct"] / 100.0
    fund_pct  = alloc["fund_pct"] / 100.0
    bond_pct  = alloc["bond_pct"] / 100.0
    repo_pct  = alloc["repo_pct"] / 100.0
    other_pct = alloc["other_pct"] / 100.0

    results = []

    print("=" * 56)
    print("  BIST ÇÖKÜŞ SENARYOLARI")
    print("=" * 56)
    print(f"  Anapara                     : {capital:,.0f} TL")
    print(f"  Hisse ağırlığı              : %{stock_pct*100:.1f}")
    print(f"  Fon ağırlığı (diğer)        : %{fund_pct*100:.1f}")
    print(f"  Tahvil ağırlığı             : %{bond_pct*100:.1f}")
    print(f"  Repo ağırlığı               : %{repo_pct*100:.1f}")
    print(f"  Diğer                       : %{other_pct*100:.1f}")
    print(f"  ───────────────────────────────────────")

    for drop_pct in BIST_CRASH_SCENARIOS:
        multiplier = drop_pct / 100.0

        # Hisse: tam çöküş
        stock_loss = capital * stock_pct * multiplier

        # Fon: BIST'in ~yarısı kadar etkilenir (konservatif)
        fund_multiplier = min(multiplier, FUND_HAIRCUT / 100.0)
        fund_loss = capital * fund_pct * fund_multiplier

        # Tahvil: hafif değer kaybı
        bond_multiplier = min(multiplier * 0.25, BOND_HAIRCUT / 100.0)
        bond_loss = capital * bond_pct * bond_multiplier

        # Repo: kayıp yok (nakit benzeri)
        repo_loss = 0.0

        # Diğer: konservatif olarak hisse gibi davran
        other_loss = capital * other_pct * multiplier

        total_loss = stock_loss + fund_loss + bond_loss + repo_loss + other_loss
        loss_ratio = (total_loss / capital) * 100.0 if capital > 0 else 0.0
        remaining = capital - total_loss

        results.append({
            "scenario": f"%{drop_pct}",
            "drop_pct": drop_pct,
            "stock_loss": round(stock_loss, 0),
            "fund_loss": round(fund_loss, 0),
            "bond_loss": round(bond_loss, 0),
            "repo_loss": round(repo_loss, 0),
            "other_loss": round(other_loss, 0),
            "total_loss": round(total_loss, 0),
            "loss_ratio": round(loss_ratio, 2),
            "remaining": round(remaining, 0),
        })

        print(
            f"  %{drop_pct:>2} çöküş  →  kayıp: {total_loss:>10,.0f} TL  "
            f"(%{loss_ratio:.1f})  |  kalan: {remaining:>10,.0f} TL"
        )

    return results


def print_stress_table(results: List[Dict[str, Any]], capital: float) -> None:
    """Stress test sonuçlarını tablo olarak yazdırır."""
    print()
    print(f"  {'Senaryo':<10} {'Hisse Kayıp':>12} {'Fon Kayıp':>12} "
          f"{'Tahvil K.':>12} {'TOPLAM':>12} {'Kalan':>14} {'Oran':>8}")
    print(f"  {'─'*10} {'─'*12} {'─'*12} {'─'*12} {'─'*12} {'─'*14} {'─'*8}")

    for r in results:
        print(
            f"  BIST {r['scenario']:<5} "
            f"{r['stock_loss']:>12,.0f} "
            f"{r['fund_loss']:>12,.0f} "
            f"{r['bond_loss']:>12,.0f} "
            f"{r['total_loss']:>12,.0f} "
            f"{r['remaining']:>14,.0f} "
            f"%{r['loss_ratio']:>6.1f}"
        )

    print()

    # En kötü senaryoda ne kadar kalıyor?
    worst = results[-1]
    print(f"  En kötü senaryoda (%{worst['drop_pct']} BIST çöküşü):")
    print(f"    Kalan portföy değeri: {worst['remaining']:,.0f} TL")
    print(f"    Toplam kayıp:        {worst['total_loss']:,.0f} TL (%{worst['loss_ratio']:.1f})")


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    """Ana akış: veri çek → ayrıştır → doğrula → stress testi yap."""
    print()
    print("╔" + "═" * 54 + "╗")
    print("║" + "  TLY FONOLOJİ STRESS TESTİ".center(54) + "║")
    print("║" + f"  {date.today().isoformat()}".center(54) + "║")
    print("╚" + "═" * 54 + "╝")

    # 1. Veri çek
    print("\n[1/4] Fonoloji'den holdings verisi çekiliyor...")
    raw = _fetch_holdings_raw()

    if raw is None:
        print("\n[HATA] Veri çekilemedi. API anahtarı / bağlantı kontrol edin.")
        print(f"  FONOLOJI_BASE_URL = {FONOLOJI_BASE_URL}")
        print(f"  FONOLOJI_API_KEY  = {'(ayarlanmış)' if FONOLOJI_API_KEY else '(BOŞ)'}")
        sys.exit(1)

    # 2. Varlık dağılımını hesapla (sadece latestPeriod)
    print("\n[2/4] Varlık dağılımı hesaplanıyor (latestPeriod filtresiyle)...")
    alloc = calculate_allocation(raw)

    if alloc is None:
        print("\n[HATA] Varlık dağılımı hesaplanamadı.")
        sys.exit(1)

    # 3. Debug çıktı ve doğrulama
    print("\n[3/4] Dağılım doğrulanıyor...")
    print_allocation_debug(alloc)
    _validate_total(alloc)

    # 4. Stress test
    print("\n[4/4] Stress testi çalıştırılıyor...")

    capital_str = os.environ.get("STRESS_TEST_CAPITAL", "")
    capital = float(capital_str) if capital_str else 500_000.0

    results = run_stress_test(alloc, capital=capital)
    print_stress_table(results, capital)

    print("─" * 56)
    print("  Test tamamlandı.")
    print()


if __name__ == "__main__":
    main()
