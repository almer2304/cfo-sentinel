"""
agents/anomaly_agent.py — AGENT 3 (NEW VERSION)
Deteksi anomali dengan membandingkan current vs baseline historis.
Dipanggil otomatis dari background pipeline.
"""

import time
from datetime import datetime, timedelta, timezone
from core.llm_client import call_llm_json
from core.database import get_connection, log_agent_step
from core.database_new import get_spending_by_category_efficient

WIB = timezone(timedelta(hours=7))

ANOMALY_SYSTEM = """
Kamu adalah Risk Analyst dan Fraud Detection Specialist dengan
pengalaman 10 tahun menganalisis pola transaksi keuangan UMKM Indonesia.

TUGASMU:
Analisis data pengeluaran per kategori dan deteksi anomali.
Bandingkan periode ini dengan baseline historis.

KRITERIA ANOMALI:
- HIGH:   deviasi > 100% dari baseline (lebih dari 2x lipat)
- MEDIUM: deviasi 50-100% dari baseline
- LOW:    deviasi 25-50% dari baseline

Jika ini data pertama (belum ada baseline), jangan buat anomali.

Balas HANYA dengan JSON:
{
  "anomalies": [
    {
      "category": "...",
      "severity": "HIGH|MEDIUM|LOW",
      "description": "penjelasan singkat dalam Bahasa Indonesia",
      "suggested_action": "saran konkret dalam 1 kalimat"
    }
  ],
  "overall_risk": "LOW|MEDIUM|HIGH|CRITICAL"
}
"""


def run_anomaly_agent(user_id: int) -> dict:
    """
    Agent 3: Deteksi anomali dengan membanding current vs baseline.
    2 query aggregate + 1 LLM call.
    """
    start = time.time()

    now     = datetime.now(WIB)
    today   = now.strftime('%Y-%m-%d')
    m_start = now.strftime('%Y-%m-01')

    three_months_ago = (now - timedelta(days=90)).strftime('%Y-%m-%d')
    last_month_end   = (now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')

    current = get_spending_by_category_efficient(user_id, m_start, today)
    baseline_raw = get_spending_by_category_efficient(
        user_id, three_months_ago, last_month_end
    )

    if not current or not baseline_raw:
        return {"anomalies": [], "overall_risk": "LOW"}

    baseline_map = {
        b["category"]: b["total"] / 3
        for b in baseline_raw
    }

    current_str = " | ".join([
        f"{c['category']}: Rp {c['total']:,.0f}"
        for c in current[:10]
    ])
    baseline_str = " | ".join([
        f"{cat}: Rp {amt:,.0f}/bulan"
        for cat, amt in list(baseline_map.items())[:10]
    ])

    prompt = (
        f"Pengeluaran bulan ini:\n{current_str}\n\n"
        f"Baseline rata-rata 3 bulan lalu:\n{baseline_str}\n\n"
        f"Deteksi anomali berdasarkan perbandingan di atas."
    )

    result, _ = call_llm_json(
        agent_name="anomaly",
        system_prompt=ANOMALY_SYSTEM,
        user_message=prompt,
    )

    anomalies = result.get("anomalies", []) if result else []

    if anomalies:
        conn = get_connection()
        cursor = conn.cursor()
        for a in anomalies:
            cat_data = next(
                (c for c in current if c["category"] == a.get("category")), {}
            )
            baseline_amt = baseline_map.get(a.get("category", ""), 0)
            current_amt  = cat_data.get("total", 0)
            deviation    = ((current_amt - baseline_amt) / max(baseline_amt, 1)) * 100

            cursor.execute("""
                INSERT INTO transaction_anomalies (
                    user_id, category, severity,
                    current_amount, baseline_amount, deviation_pct,
                    description, suggested_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                a.get("category", ""),
                a.get("severity", "LOW"),
                current_amt, baseline_amt, round(deviation, 1),
                a.get("description", ""),
                a.get("suggested_action", ""),
            ))

        has_critical = any(a.get("severity") == "HIGH" for a in anomalies)
        cursor.execute("""
            UPDATE daily_summaries
            SET anomaly_count        = ?,
                has_critical_anomaly = ?
            WHERE user_id = ? AND date_only = ?
        """, (len(anomalies), 1 if has_critical else 0, user_id, today))

        conn.commit()
        conn.close()

    duration = int((time.time() - start) * 1000)
    log_agent_step(
        session_id=f"anomaly-{user_id}-{today}",
        agent_name="anomaly",
        step=3,
        input_summary=f"Current: {len(current)} kategori, Baseline: {len(baseline_raw)} kategori",
        reasoning=f"Found {len(anomalies)} anomalies. Risk: {result.get('overall_risk', 'LOW') if result else 'LOW'}",
        output_summary=str(anomalies[:2]),
        duration_ms=duration,
        status="success" if result else "fallback",
        user_id=user_id,
    )

    return result or {"anomalies": [], "overall_risk": "LOW"}
