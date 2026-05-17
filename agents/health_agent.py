"""
agents/health_agent.py — AGENT 2
Hitung health score dan buat narasi keuangan harian.
Dipanggil otomatis dari background pipeline.
"""

import time
from datetime import datetime, timedelta, timezone
from core.llm_client import call_llm
from core.database import get_connection, log_agent_step
from core.database_new import (
    get_financial_summary, get_cash_balance,
)

WIB = timezone(timedelta(hours=7))

HEALTH_SYSTEM = """
Kamu adalah Financial Analyst dengan pengalaman 12 tahun menganalisis
kesehatan keuangan UMKM Indonesia. Kamu ahli dalam menerjemahkan
angka-angka keuangan menjadi narasi yang mudah dipahami oleh
pemilik usaha kecil yang tidak berlatar belakang keuangan.

TUGASMU:
Buat narasi singkat kondisi keuangan berdasarkan data yang diberikan.
Maksimal 2 kalimat. Gunakan bahasa sehari-hari yang hangat.
Sebutkan angka yang paling penting dan satu tindakan yang paling mendesak.

ATURAN KETAT:
- HANYA gunakan angka dari data yang diberikan
- Jangan mengarang angka atau asumsi
- Jika data tidak cukup, katakan "Data belum cukup untuk analisis"
- Bahasa Indonesia sehari-hari, bukan istilah teknis

Balas HANYA dengan teks narasi, tanpa JSON, tanpa format tambahan.
"""


def compute_health_score(summary: dict, cash_balance: float) -> float:
    income  = summary.get("total_income", 0) or 0
    expense = summary.get("total_expense", 0) or 0
    actual_expense = (
        (summary.get("operational_expense", 0) or 0) +
        (summary.get("cogs", 0) or 0)
    )

    # Komponen 1: Gross margin (bobot 30%)
    if income > 0:
        margin = max(0, (income - actual_expense) / income * 100)
        margin_score = min(30, (margin / 30) * 30)
    else:
        margin_score = 0

    # Komponen 2: Runway (bobot 35%)
    burn_30d = expense
    if burn_30d > 0 and cash_balance > 0:
        runway = (cash_balance / burn_30d) * 30
    else:
        runway = 0 if cash_balance <= 0 else 90
    runway_score = min(35, (runway / 60) * 35)

    # Komponen 3: Cash flow positif (bobot 25%)
    net = income - expense
    cashflow_score = 25 if net >= 0 else max(0, 25 + (net / max(expense, 1)) * 25)

    # Komponen 4: Ada transaksi (bobot 10%)
    activity_score = 10 if (summary.get("total_tx", 0) or 0) > 0 else 0

    total = margin_score + runway_score + cashflow_score + activity_score
    return round(min(100, max(0, total)), 1)


def run_health_agent(user_id: int) -> dict:
    """
    Agent 2: Hitung health score dan buat narasi.
    2 query aggregate + 1 LLM call untuk narasi.
    """
    start = time.time()

    today = datetime.now(WIB).strftime('%Y-%m-%d')
    month_start = datetime.now(WIB).strftime('%Y-%m-01')

    summary = get_financial_summary(user_id, month_start, today)
    cash_balance = get_cash_balance(user_id)

    health_score = compute_health_score(summary, cash_balance)

    income   = summary.get("total_income", 0) or 0
    expense  = summary.get("total_expense", 0) or 0
    net      = income - expense
    burn_day = expense / max(summary.get("active_days", 1) or 1, 1)
    runway   = round(cash_balance / burn_day) if burn_day > 0 else 999

    data_str = (
        f"Health Score: {health_score}/100 | "
        f"Pemasukan bulan ini: Rp {income:,.0f} | "
        f"Pengeluaran bulan ini: Rp {expense:,.0f} | "
        f"Saldo kas: Rp {cash_balance:,.0f} | "
        f"Uang habis per hari: Rp {burn_day:,.0f} | "
        f"Perkiraan bertahan: {runway} hari"
    )

    narrative, _ = call_llm(
        agent_name="health",
        system_prompt=HEALTH_SYSTEM,
        user_message=f"Buat narasi singkat kondisi keuangan:\n{data_str}",
        response_format="text",
    )

    # Simpan ke daily_summaries
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_summaries (
            user_id, date_only, total_income, total_expense,
            net_cashflow, operational_expense, cogs, asset_purchase,
            transaction_count, health_score, runway_days,
            burn_rate_daily, agent_narrative
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date_only) DO UPDATE SET
            total_income        = excluded.total_income,
            total_expense       = excluded.total_expense,
            net_cashflow        = excluded.net_cashflow,
            operational_expense = excluded.operational_expense,
            cogs                = excluded.cogs,
            asset_purchase      = excluded.asset_purchase,
            transaction_count   = excluded.transaction_count,
            health_score        = excluded.health_score,
            runway_days         = excluded.runway_days,
            burn_rate_daily     = excluded.burn_rate_daily,
            agent_narrative     = excluded.agent_narrative,
            processed_at        = datetime('now','localtime')
    """, (
        user_id, today, income, expense, net,
        summary.get("operational_expense", 0) or 0,
        summary.get("cogs", 0) or 0,
        summary.get("asset_purchase", 0) or 0,
        summary.get("total_tx", 0) or 0,
        health_score, runway, burn_day,
        narrative or "",
    ))
    conn.commit()
    conn.close()

    duration = int((time.time() - start) * 1000)
    log_agent_step(
        session_id=f"health-{user_id}-{today}",
        agent_name="health",
        step=2,
        input_summary=f"user_id={user_id}, period={month_start} to {today}",
        reasoning=f"Score: {health_score}, Runway: {runway}d, Net: {net:,.0f}",
        output_summary=narrative[:100] if narrative else "",
        duration_ms=duration,
        status="success",
        user_id=user_id,
    )

    return {
        "health_score": health_score,
        "runway_days": runway,
        "burn_rate_daily": burn_day,
        "cash_balance": cash_balance,
        "narrative": narrative,
    }
