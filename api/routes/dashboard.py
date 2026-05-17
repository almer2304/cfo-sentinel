"""
api/routes/dashboard.py
Dashboard otomatis — ambil data dari daily_summaries yang sudah dihitung
oleh background pipeline. TANPA trigger LLM manual.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from api.models.response import BaseResponse
from api.middleware.auth import get_current_user
from core.database_new import (
    get_daily_summary,
    get_health_history,
    get_unresolved_anomalies,
    get_financial_summary,
    get_cash_balance,
    get_spending_by_category_efficient,
)
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

WIB = timezone(timedelta(hours=7))


@router.get("", response_model=BaseResponse)
async def get_dashboard(
    current_user: dict = Depends(get_current_user),
):
    """
    Dashboard utama — data dihitung otomatis oleh pipeline.
    Satu call, semua data yang dibutuhkan homepage.
    """
    user_id = current_user["id"]
    now = datetime.now(WIB)
    today = now.strftime('%Y-%m-%d')
    month_start = now.strftime('%Y-%m-01')

    # Data dari pipeline (sudah dihitung)
    summary_today = get_daily_summary(user_id, today)

    # Fallback: hitung live dari DB jika pipeline belum jalan
    if not summary_today:
        financial = get_financial_summary(user_id, month_start, today)
        cash_balance = get_cash_balance(user_id)
        expense = financial.get("total_expense", 0) or 0
        income  = financial.get("total_income", 0) or 0
        active_days = max(financial.get("active_days", 1) or 1, 1)
        burn_day = expense / active_days
        runway = round(cash_balance / burn_day) if burn_day > 0 else 999

        summary_today = {
            "health_score":      0,
            "runway_days":       runway,
            "burn_rate_daily":   burn_day,
            "total_income":      income,
            "total_expense":     expense,
            "net_cashflow":      income - expense,
            "agent_narrative":   "Belum ada analisis hari ini. Tambah transaksi untuk memulai.",
            "anomaly_count":     0,
            "has_critical_anomaly": 0,
        }

    cash_balance = get_cash_balance(user_id)
    anomalies    = get_unresolved_anomalies(user_id, limit=3)
    health_hist  = get_health_history(user_id, days=7)

    # Trend health score
    trend = "STABLE"
    if len(health_hist) >= 2:
        latest  = health_hist[0].get("health_score", 0)
        prev    = health_hist[1].get("health_score", 0)
        diff    = latest - prev
        trend   = "UP" if diff > 2 else ("DOWN" if diff < -2 else "STABLE")

    health_score = summary_today.get("health_score", 0)
    status = (
        "DANGER"  if health_score < 40 else
        "WARNING" if health_score < 65 else
        "SAFE"
    )

    return BaseResponse(
        success=True,
        data={
            "health": {
                "score":   health_score,
                "status":  status,
                "trend":   trend,
            },
            "metrics": {
                "cash_balance":    cash_balance,
                "total_income":    summary_today.get("total_income", 0),
                "total_expense":   summary_today.get("total_expense", 0),
                "net_cashflow":    summary_today.get("net_cashflow", 0),
                "burn_rate_daily": summary_today.get("burn_rate_daily", 0),
                "runway_days":     summary_today.get("runway_days", 0),
            },
            "narrative":     summary_today.get("agent_narrative", ""),
            "anomaly_count": summary_today.get("anomaly_count", 0),
            "has_critical":  bool(summary_today.get("has_critical_anomaly", 0)),
            "anomalies":     anomalies,
            "health_history": health_hist,
            "last_updated":  summary_today.get("processed_at", ""),
        },
    )


@router.get("/spending", response_model=BaseResponse)
async def get_spending_breakdown(
    date_from: Optional[str] = Query(default=None),
    date_to:   Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Pengeluaran per kategori (untuk chart pie/bar)."""
    user_id = current_user["id"]
    now = datetime.now(WIB)

    df = date_from or now.strftime('%Y-%m-01')
    dt = date_to   or now.strftime('%Y-%m-%d')

    spending = get_spending_by_category_efficient(user_id, df, dt)
    return BaseResponse(success=True, data=spending)


@router.get("/health-history", response_model=BaseResponse)
async def get_health_history_route(
    days: int = Query(default=30, ge=7, le=90),
    current_user: dict = Depends(get_current_user),
):
    """Riwayat health score untuk chart tren."""
    data = get_health_history(current_user["id"], days=days)
    return BaseResponse(success=True, data=data)


@router.get("/anomalies", response_model=BaseResponse)
async def get_anomalies(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Daftar anomali yang belum resolved."""
    data = get_unresolved_anomalies(current_user["id"], limit=limit)
    return BaseResponse(success=True, data=data)
