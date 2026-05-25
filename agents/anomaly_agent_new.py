"""
agents/anomaly_agent_new.py - Agent 3

Deteksi anomali deterministik. LLM tidak dipakai sebagai sumber keputusan
risiko karena kategori, deviasi, dan severity harus reproducible.
"""

import time
from datetime import datetime, timedelta, timezone

from core.database import get_connection, log_agent_step
from core.database_new import get_spending_by_category_efficient

WIB = timezone(timedelta(hours=7))


def _severity_from_deviation(deviation_pct: float, current_amount: float) -> str | None:
    dev = abs(deviation_pct)
    if dev >= 100 or current_amount >= 10_000_000:
        return "HIGH"
    if dev >= 50 or current_amount >= 5_000_000:
        return "MEDIUM"
    if dev >= 25:
        return "LOW"
    return None


def _description(category: str, current: float, baseline: float, deviation: float) -> str:
    if baseline <= 0:
        return f"Kategori {category} muncul bulan ini sebesar Rp {current:,.0f} tanpa baseline historis."
    direction = "naik" if deviation > 0 else "turun"
    return (
        f"Pengeluaran {category} {direction} {abs(deviation):.0f}% dari baseline "
        f"Rp {baseline:,.0f} menjadi Rp {current:,.0f}."
    )


def _action(category: str, severity: str, deviation: float) -> str:
    if severity == "HIGH":
        return "Cek bukti transaksi hari ini dan tahan pengeluaran sejenis sampai penyebabnya jelas."
    if deviation > 0:
        return f"Bandingkan {category} dengan kebutuhan operasional minggu ini; potong yang tidak langsung menghasilkan penjualan."
    return f"Pastikan penurunan {category} bukan karena stok/supplier yang menghambat penjualan."


def _overall_risk(anomalies: list[dict]) -> str:
    if any(a["severity"] == "HIGH" and a["current_amount"] >= 10_000_000 for a in anomalies):
        return "CRITICAL"
    if any(a["severity"] == "HIGH" for a in anomalies):
        return "HIGH"
    if any(a["severity"] == "MEDIUM" for a in anomalies):
        return "MEDIUM"
    return "LOW"


def run_anomaly_agent(user_id: int) -> dict:
    """
    Agent 3: current month spending vs rolling 90-day baseline.
    """
    start = time.time()
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    three_months_ago = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    last_month_end = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")

    current = get_spending_by_category_efficient(user_id, month_start, today)
    baseline_raw = get_spending_by_category_efficient(user_id, three_months_ago, last_month_end)

    baseline_map = {
        b["category"]: (b["total"] or 0) / 3
        for b in baseline_raw
    }

    anomalies: list[dict] = []
    for row in current:
        category = row["category"]
        current_amount = row["total"] or 0
        baseline_amount = baseline_map.get(category, 0)

        if baseline_amount > 0:
            deviation = ((current_amount - baseline_amount) / baseline_amount) * 100
            severity = _severity_from_deviation(deviation, current_amount)
        else:
            deviation = 100.0 if current_amount > 0 else 0.0
            # Bulan pertama: hanya flag kategori baru jika nominalnya material.
            severity = "MEDIUM" if current_amount >= 5_000_000 else None

        if not severity:
            continue

        anomalies.append({
            "category": category,
            "severity": severity,
            "current_amount": round(current_amount, 2),
            "baseline_amount": round(baseline_amount, 2),
            "deviation_pct": round(deviation, 1),
            "description": _description(category, current_amount, baseline_amount, deviation),
            "suggested_action": _action(category, severity, deviation),
        })

    anomalies.sort(
        key=lambda a: (
            {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(a["severity"], 3),
            -abs(a["deviation_pct"]),
            -a["current_amount"],
        )
    )
    risk = _overall_risk(anomalies)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Hindari duplikasi karena pipeline berjalan setiap transaksi.
        cursor.execute("""
            DELETE FROM transaction_anomalies
            WHERE user_id = ? AND date(detected_at) = ? AND is_resolved = 0
        """, (user_id, today))

        for a in anomalies:
            cursor.execute("""
                INSERT INTO transaction_anomalies (
                    user_id, category, severity,
                    current_amount, baseline_amount, deviation_pct,
                    description, suggested_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                a["category"],
                a["severity"],
                a["current_amount"],
                a["baseline_amount"],
                a["deviation_pct"],
                a["description"],
                a["suggested_action"],
            ))

        has_critical = risk in {"HIGH", "CRITICAL"}
        cursor.execute("""
            UPDATE daily_summaries
            SET anomaly_count = ?,
                has_critical_anomaly = ?
            WHERE user_id = ? AND date_only = ?
        """, (len(anomalies), 1 if has_critical else 0, user_id, today))
        conn.commit()
    finally:
        conn.close()

    duration = int((time.time() - start) * 1000)
    log_agent_step(
        session_id=f"anomaly-{user_id}-{today}",
        agent_name="anomaly",
        step=3,
        input_summary=f"Current: {len(current)} kategori, baseline: {len(baseline_raw)} kategori",
        reasoning=f"Deterministic deviation check. Found {len(anomalies)} anomalies. Risk: {risk}",
        output_summary=str(anomalies[:2]),
        duration_ms=duration,
        status="success",
        user_id=user_id,
    )

    return {"anomalies": anomalies, "overall_risk": risk}
