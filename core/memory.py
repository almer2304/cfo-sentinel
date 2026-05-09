"""
core/memory.py
CFO Sentinel — Persistent Memory Layer

Handles semua logic yang berhubungan dengan memori historis:
- Load baseline per kategori
- Update baseline setelah analisis baru
- Ambil konteks historis untuk agent
- Generate synthetic baseline untuk cold start
"""

import json
import math
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

try:
    from core.database import (
        get_spending_baselines,
        save_baseline,
        get_monthly_snapshots,
        save_monthly_snapshot,
        get_transactions,
        get_spending_by_category,
    )
except ImportError:
    from database import (
        get_spending_baselines,
        save_baseline,
        get_monthly_snapshots,
        save_monthly_snapshot,
        get_transactions,
        get_spending_by_category,
    )

# Baseline industri (hardcoded berdasarkan riset UMKM Indonesia)
# Dalam persen dari total pengeluaran per kategori
INDUSTRY_BASELINES = {
    "kuliner": {
        "health_score_avg": 72,
        "categories": {
            "Bahan Baku":   {"pct": 45, "std_pct": 8},
            "Operasional":  {"pct": 20, "std_pct": 5},
            "SDM":          {"pct": 15, "std_pct": 4},
            "Marketing":    {"pct": 8,  "std_pct": 4},
            "Lain-lain":    {"pct": 12, "std_pct": 5},
        }
    },
    "fashion": {
        "health_score_avg": 68,
        "categories": {
            "Bahan Baku":   {"pct": 40, "std_pct": 8},
            "Operasional":  {"pct": 18, "std_pct": 5},
            "SDM":          {"pct": 20, "std_pct": 5},
            "Marketing":    {"pct": 12, "std_pct": 5},
            "Lain-lain":    {"pct": 10, "std_pct": 4},
        }
    },
    "jasa": {
        "health_score_avg": 75,
        "categories": {
            "SDM":          {"pct": 50, "std_pct": 10},
            "Operasional":  {"pct": 20, "std_pct": 6},
            "Marketing":    {"pct": 15, "std_pct": 6},
            "Bahan Baku":   {"pct": 5,  "std_pct": 3},
            "Lain-lain":    {"pct": 10, "std_pct": 4},
        }
    },
    "retail": {
        "health_score_avg": 65,
        "categories": {
            "Bahan Baku":   {"pct": 55, "std_pct": 8},
            "Operasional":  {"pct": 20, "std_pct": 5},
            "SDM":          {"pct": 12, "std_pct": 4},
            "Marketing":    {"pct": 8,  "std_pct": 4},
            "Lain-lain":    {"pct": 5,  "std_pct": 3},
        }
    },
    "general": {
        "health_score_avg": 70,
        "categories": {
            "Bahan Baku":   {"pct": 35, "std_pct": 10},
            "Operasional":  {"pct": 25, "std_pct": 7},
            "SDM":          {"pct": 20, "std_pct": 7},
            "Marketing":    {"pct": 10, "std_pct": 5},
            "Lain-lain":    {"pct": 10, "std_pct": 5},
        }
    },
}


def get_industry_health_avg(business_type: str) -> float:
    """Ambil rata-rata health score industri sejenis."""
    bt = business_type.lower() if business_type else "general"
    data = INDUSTRY_BASELINES.get(bt, INDUSTRY_BASELINES["general"])
    return data["health_score_avg"]


def load_baselines_for_analysis(business_type: str) -> list[dict]:
    """
    Load baseline dari database.
    Jika belum ada (cold start), gunakan industry baseline.
    """
    db_baselines = get_spending_baselines(business_type)

    if db_baselines:
        return db_baselines

    # Cold start — generate dari industry baseline
    return generate_cold_start_baselines(business_type, total_monthly_expense=5000000)


def generate_cold_start_baselines(
    business_type: str,
    total_monthly_expense: float = 5000000
) -> list[dict]:
    """
    Buat baseline awal berdasarkan rata-rata industri.
    Dipanggil saat tidak ada data historis (user baru).
    """
    bt = business_type.lower()
    industry = INDUSTRY_BASELINES.get(bt, INDUSTRY_BASELINES["general"])

    baselines = []
    for category, data in industry["categories"].items():
        avg_monthly = total_monthly_expense * (data["pct"] / 100)
        std_deviation = avg_monthly * (data["std_pct"] / 100)

        # Simpan ke database
        save_baseline(
            category=category,
            business_type=business_type,
            avg_monthly=avg_monthly,
            std_deviation=std_deviation,
            sample_months=0,  # 0 = synthetic, bukan dari data real
        )

        baselines.append({
            "category": category,
            "business_type": business_type,
            "avg_monthly": avg_monthly,
            "std_deviation": std_deviation,
            "sample_months": 0,
        })

    return baselines


def update_baselines_from_transactions(
    business_type: str,
    year_month: str
) -> None:
    """
    Update baseline setelah ada data transaksi baru.
    Dipanggil di akhir setiap sesi analisis.
    """
    # Ambil semua snapshot historis
    snapshots = get_monthly_snapshots(business_type, last_n_months=6)
    if not snapshots:
        return

    # Hitung rata-rata dan std deviation per kategori
    # dari data transaksi 3 bulan terakhir
    three_months_ago = (
        datetime.strptime(year_month, "%Y-%m") -
        relativedelta(months=3)
    ).strftime("%Y-%m-01")

    spending = get_spending_by_category(
        start_date=three_months_ago,
        business_type=business_type,
    )

    if not spending:
        return

    # Hitung bulan yang di-cover
    sample_months = min(len(snapshots), 3)

    for item in spending:
        category = item["category"]
        if not category:
            continue

        avg_monthly = item["total"] / sample_months

        # Std deviation sederhana — 15% dari rata-rata jika belum ada data
        existing = get_spending_baselines(business_type)
        existing_map = {b["category"]: b for b in existing}

        if category in existing_map and existing_map[category]["sample_months"] > 0:
            # Update dengan weighted average
            old = existing_map[category]
            new_avg = (old["avg_monthly"] * 0.6) + (avg_monthly * 0.4)
            std_dev = abs(new_avg - old["avg_monthly"]) * 0.5 + old["std_deviation"] * 0.5
        else:
            new_avg = avg_monthly
            std_dev = avg_monthly * 0.15

        save_baseline(
            category=category,
            business_type=business_type,
            avg_monthly=new_avg,
            std_deviation=std_dev,
            sample_months=sample_months,
        )


def get_historical_context(business_type: str) -> str:
    """
    Buat ringkasan konteks historis untuk Advisor Agent.
    Returns string yang di-inject ke prompt.
    """
    snapshots = get_monthly_snapshots(business_type, last_n_months=3)

    if not snapshots:
        return "Ini adalah analisis pertama. Belum ada data historis."

    lines = []
    for s in snapshots:
        lines.append(
            f"- {s['year_month']}: "
            f"Income Rp {s['total_income']:,.0f} | "
            f"Expense Rp {s['total_expense']:,.0f} | "
            f"Health Score {s['health_score']:.0f}/100 | "
            f"Runway {s['runway_days']:.0f} hari"
        )

    # Deteksi tren
    if len(snapshots) >= 2:
        latest = snapshots[0]["health_score"]
        prev   = snapshots[1]["health_score"]
        diff   = latest - prev

        if diff > 5:
            trend = f"📈 Health score membaik {diff:.0f} poin dari bulan lalu."
        elif diff < -5:
            trend = f"📉 Health score memburuk {abs(diff):.0f} poin dari bulan lalu."
        else:
            trend = "➡️  Health score relatif stabil."

        lines.append(f"\nTren: {trend}")

    return "\n".join(lines)


def save_session_snapshot(
    analytics: dict,
    business_type: str
) -> None:
    """
    Simpan snapshot bulanan setelah analisis selesai.
    Dipanggil oleh Orchestrator di akhir pipeline.
    """
    year_month = datetime.now().strftime("%Y-%m")

    save_monthly_snapshot({
        "year_month":    year_month,
        "total_income":  analytics.get("total_income", 0),
        "total_expense": analytics.get("total_expense", 0),
        "net_cashflow":  analytics.get("net_cashflow", 0),
        "health_score":  analytics.get("health_score", 0),
        "burn_rate":     analytics.get("burn_rate_monthly", 0),
        "runway_days":   analytics.get("runway_days", 0),
        "business_type": business_type,
    })


def calculate_anomaly_threshold(
    category: str,
    business_type: str,
    current_amount: float,
) -> dict:
    """
    Hitung apakah current_amount adalah anomali berdasarkan baseline.
    Returns dict dengan info anomali atau None jika normal.
    """
    baselines = load_baselines_for_analysis(business_type)
    baseline_map = {b["category"]: b for b in baselines}

    if category not in baseline_map:
        return {"is_anomaly": False, "reason": "Tidak ada baseline untuk kategori ini"}

    b = baseline_map[category]
    avg    = b["avg_monthly"]
    std    = b["std_deviation"] or (avg * 0.15)

    if avg == 0:
        return {"is_anomaly": False, "reason": "Baseline nol"}

    deviation_pct = ((current_amount - avg) / avg) * 100
    z_score       = (current_amount - avg) / std if std > 0 else 0

    is_anomaly = abs(z_score) > 2 or abs(deviation_pct) > 50

    severity = "LOW"
    if abs(deviation_pct) >= 100:
        severity = "HIGH"
    elif abs(deviation_pct) >= 50:
        severity = "MEDIUM"

    return {
        "is_anomaly":     is_anomaly,
        "baseline_amount": avg,
        "deviation_pct":  round(deviation_pct, 1),
        "z_score":        round(z_score, 2),
        "severity":       severity if is_anomaly else None,
        "sample_months":  b.get("sample_months", 0),
        "is_synthetic":   b.get("sample_months", 0) == 0,
    }


if __name__ == "__main__":
    from database import init_database
    init_database()

    print("Testing memory layer...")

    # Test cold start
    baselines = generate_cold_start_baselines("kuliner", 8000000)
    print(f"\n✅ Cold start baselines generated for 'kuliner':")
    for b in baselines:
        print(f"   {b['category']:15} → avg Rp {b['avg_monthly']:>10,.0f}/bulan")

    # Test industry avg
    for bt in ["kuliner", "fashion", "jasa", "retail"]:
        avg = get_industry_health_avg(bt)
        print(f"   Health score avg {bt:10}: {avg}/100")

    # Test anomaly threshold
    result = calculate_anomaly_threshold("Operasional", "kuliner", 4000000)
    print(f"\n✅ Anomaly check — Operasional Rp 4.000.000:")
    print(f"   Is anomaly: {result['is_anomaly']}")
    print(f"   Deviation:  {result['deviation_pct']}%")
    print(f"   Severity:   {result.get('severity', 'Normal')}")