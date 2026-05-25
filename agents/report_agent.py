"""
agents/report_agent.py — AGENT 5
Business Intelligence: Ringkasan harian & update agent_narrative.
Dipanggil dari background pipeline setelah Agent 1-3 selesai.
"""

import time
from datetime import datetime, timedelta, timezone
from core.llm_client import call_llm
from core.database import get_connection, log_agent_step
from core.database_new import get_financial_summary, get_daily_summary, get_cash_balance
from core.prompts import REPORT_SYSTEM
from core.finance_rules import safe_finance_narrative

WIB = timezone(timedelta(hours=7))


def run_report_agent(user_id: int, date_str: str) -> str:
    """
    Agent 5: Buat ringkasan harian dan update agent_narrative di daily_summaries.
    Dipanggil dari pipeline setelah Agent 1-3 selesai.
    EFISIENSI: 2 query aggregate + 1 LLM call untuk narasi teks.
    """
    start = time.time()

    # Query 1: Summary finansial hari ini
    summary = get_financial_summary(user_id, date_str, date_str)
    income   = summary.get("total_income", 0) or 0
    expense  = summary.get("total_expense", 0) or 0
    net      = income - expense
    tx_count = summary.get("total_tx", 0) or 0

    # Query 2: Data health score dari daily_summaries (hasil Agent 2)
    daily = get_daily_summary(user_id, date_str)
    health_score = daily.get("health_score", 0) if daily else 0
    runway_days  = daily.get("runway_days", 0) if daily else 0
    anomaly_count = daily.get("anomaly_count", 0) if daily else 0
    cash_balance = get_cash_balance(user_id)

    # Jika tidak ada transaksi hari ini, skip LLM call
    if tx_count == 0:
        narrative = "Belum ada transaksi hari ini. Mulai catat transaksi untuk mendapatkan analisis."
        _update_narrative(user_id, date_str, narrative)
        return narrative

    # Build data string untuk LLM — HANYA angka yang relevan, hemat token
    data_str = (
        f"Tanggal: {date_str} | "
        f"Transaksi hari ini: {tx_count} transaksi | "
        f"Pemasukan: Rp {income:,.0f} | "
        f"Pengeluaran: Rp {expense:,.0f} | "
        f"Arus kas bersih: Rp {net:+,.0f} | "
        f"Health Score: {health_score:.0f}/100 | "
        f"Perkiraan bertahan: {runway_days:.0f} hari | "
        f"Anomali terdeteksi: {anomaly_count}"
    )

    fallback_narrative = safe_finance_narrative(
        summary,
        cash_balance=cash_balance,
        health_score=health_score,
        runway_days=runway_days,
    )
    try:
        narrative, _ = call_llm(
            agent_name="report",
            system_prompt=REPORT_SYSTEM,
            user_message=f"Buat ringkasan harian berdasarkan data berikut:\n{data_str}",
            response_format="text",
        )
    except Exception as e:
        print(f"[Report Agent] LLM fallback: {e}")
        narrative = fallback_narrative

    # Bersihkan jika ada think block yang lolos (defensive)
    import re
    if narrative:
        narrative = re.sub(r'<think>.*?</think>', '', narrative, flags=re.DOTALL).strip()

    narrative = narrative or fallback_narrative or "Analisis harian selesai diproses."

    # Update kolom agent_narrative di daily_summaries
    _update_narrative(user_id, date_str, narrative)

    duration = int((time.time() - start) * 1000)
    log_agent_step(
        session_id=f"report-{user_id}-{date_str}",
        agent_name="report",
        step=5,
        input_summary=f"user_id={user_id}, date={date_str}, tx_count={tx_count}",
        reasoning=f"Income={income:,.0f}, Expense={expense:,.0f}, Health={health_score}",
        output_summary=narrative[:100],
        duration_ms=duration,
        status="success",
        user_id=user_id,
    )

    print(f"[PIPELINE] Agent 5 Report OK → {narrative[:60]}... [user={user_id}]")
    return narrative


def _update_narrative(user_id: int, date_str: str, narrative: str):
    """Update kolom agent_narrative di daily_summaries untuk tanggal ini."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Coba update dulu — jika row sudah ada dari Agent 2
        cursor.execute("""
            UPDATE daily_summaries
            SET agent_narrative = ?,
                processed_at    = datetime('now','localtime')
            WHERE user_id = ? AND date_only = ?
        """, (narrative, user_id, date_str))

        # Jika belum ada row (Agent 2 belum jalan), insert minimal
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO daily_summaries (user_id, date_only, agent_narrative)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, date_only) DO UPDATE SET
                    agent_narrative = excluded.agent_narrative,
                    processed_at    = datetime('now','localtime')
            """, (user_id, date_str, narrative))

        conn.commit()
    except Exception as e:
        print(f"[Report Agent] DB update error: {e}")
    finally:
        conn.close()
