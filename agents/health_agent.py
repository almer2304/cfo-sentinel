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
from core.finance_rules import estimate_health_score, safe_finance_narrative

WIB = timezone(timedelta(hours=7))

HEALTH_SYSTEM = """
Kamu adalah Financial Controller (Pengawas Keuangan) Virtual untuk UMKM Indonesia.
Tugasmu adalah memberikan "Diagnostic Report" singkat (2 kalimat) tentang kesehatan
bisnis berdasarkan data akuntansi terbaru.

══════════════════════════════════════════════
FOCUS ANALISIS CONTROLLER:
══════════════════════════════════════════════
1. LABA vs KAS: Bedakan apakah bisnis untung secara operasional meskipun kas mungkin menipis.
2. EFISIENSI: Pantau apakah beban operasional (listrik, gaji, sewa) wajar terhadap pendapatan.
3. KESEHATAN NERACA: Pantau pergerakan piutang dan stok (persediaan).

ATURAN NARASI:
- Maksimal 2 kalimat.
- Harus menyebutkan angka kunci (Profit Margin, Runway, atau Rasio Kas).
- Gunakan bahasa yang tegas namun mendukung (Sahabat Bisnis).
- Jangan menakut-nakuti, berikan fakta akuntansi yang murni.
"""


def compute_health_score(summary: dict, cash_balance: float) -> float:
    return estimate_health_score(summary, cash_balance)


def run_health_agent(user_id: int) -> dict:
    """
    Agent 2: Hitung health score dan buat narasi.
    2 query aggregate + 1 LLM call untuk narasi.
    """
    start = time.time()

    today = datetime.now(WIB).strftime('%Y-%m-%d')
    month_start = datetime.now(WIB).strftime('%Y-%m-01')

    # Financial summary for the WHOLE MONTH
    financial = get_financial_summary(user_id, month_start, today)
    
    # Financial summary for TODAY specifically (to update history card correctly)
    summary_today = get_financial_summary(user_id, today, today)
    
    cash_balance = get_cash_balance(user_id)

    health_score = compute_health_score(financial, cash_balance)

    income_month  = financial.get("total_income", 0) or 0
    expense_month = financial.get("total_expense", 0) or 0
    net_month     = income_month - expense_month
    burn_base     = (
        (financial.get("operational_expense", 0) or 0)
        + (financial.get("cogs", 0) or 0)
    ) or expense_month
    burn_day      = burn_base / max(financial.get("active_days", 1) or 1, 1)
    if cash_balance <= 0:
        runway = 0
    elif burn_day > 0:
        runway = min(round(cash_balance / burn_day), 180)
    else:
        runway = 180 if (financial.get("total_tx", 0) or 0) > 0 else 0

    # Data for the history card (Today's performance)
    income_today  = summary_today.get("total_income", 0) or 0
    expense_today = summary_today.get("total_expense", 0) or 0
    net_today     = income_today - expense_today

    data_str = (
        f"Health Score: {health_score}/100 | "
        f"Pemasukan hari ini: Rp {income_today:,.0f} | "
        f"Pengeluaran hari ini: Rp {expense_today:,.0f} | "
        f"Arus kas bulan ini: Rp {net_month:+,.0f} | "
        f"Pendapatan jurnal bulan ini: Rp {financial.get('journal_revenue', 0) or 0:,.0f} | "
        f"Beban jurnal bulan ini: Rp {financial.get('journal_expense', 0) or 0:,.0f} | "
        f"Saldo kas saat ini: Rp {cash_balance:,.0f} | "
        f"Runway: {runway} hari"
    )

    fallback_narrative = safe_finance_narrative(
        financial, cash_balance, health_score, runway
    )
    try:
        narrative, _ = call_llm(
            agent_name="health",
            system_prompt=HEALTH_SYSTEM,
            user_message=f"Buat narasi singkat kondisi keuangan:\n{data_str}",
            response_format="text",
        )
    except Exception as e:
        print(f"[Health Agent] LLM fallback: {e}")
        narrative = fallback_narrative

    narrative = (narrative or fallback_narrative).strip()

    # Simpan ke daily_summaries (Update dengan data TERBARU harian)
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
        user_id, today, income_today, expense_today, net_today,
        summary_today.get("operational_expense", 0) or 0,
        summary_today.get("cogs", 0) or 0,
        summary_today.get("asset_purchase", 0) or 0,
        summary_today.get("total_tx", 0) or 0,
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
        reasoning=f"Score: {health_score}, Runway: {runway}d, Net month: {net_month:,.0f}",
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
