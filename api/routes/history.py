from fastapi import APIRouter, Depends, Query
from api.models.response import HistoryItem, BaseResponse, AnomalyData, ActionItemData
from api.middleware.auth import get_current_user
from core.database import (
    get_connection, get_anomalies, get_recommendations
)

router = APIRouter(prefix="/history", tags=["History"])


@router.get("/list", response_model=list[HistoryItem])
async def get_history(
    limit: int = Query(default=10, le=50),
    current_user: dict = Depends(get_current_user),
):
    """
    Ambil riwayat analisis user. 
    Menggabungkan data dari daily_summaries (otomatis) dan analytics (manual).
    """
    user_id = current_user["id"]
    conn = get_connection()
    cursor = conn.cursor()

    # Ambil dari daily_summaries (Analisis harian otomatis dari pipeline)
    cursor.execute("""
        SELECT 
            'DAILY-' || date_only as session_id,
            date_only || ' 23:59:59' as created_at,
            health_score, total_income, total_expense, net_cashflow,
            runway_days, agent_narrative as narrative
        FROM daily_summaries
        WHERE user_id = ?
        ORDER BY date_only DESC
        LIMIT ?
    """, (user_id, limit))

    rows = cursor.fetchall()
    
    # Ambil saldo kas saat ini untuk context
    from core.database_new import get_cash_balance
    current_balance = get_cash_balance(user_id)

    result = []
    for row in rows:
        hs = row["health_score"] or 0
        status = "SAFE" if hs >= 65 else ("WARNING" if hs >= 50 else "DANGER")
        
        # Untuk daily summary, kita ambil anomali berdasarkan tanggal
        date_str = row["session_id"].replace("DAILY-", "")
        cursor.execute("""
            SELECT category, severity, description, deviation_pct
            FROM transaction_anomalies
            WHERE user_id = ? AND date(detected_at) = ?
        """, (user_id, date_str))
        anoms = cursor.fetchall()

        result.append(HistoryItem(
            session_id=row["session_id"],
            created_at=row["created_at"],
            health_score=hs,
            health_status=status,
            total_income=row["total_income"] or 0,
            total_expense=row["total_expense"] or 0,
            net_cashflow=row["net_cashflow"] or 0,
            cash_balance=current_balance, # Fallback to current
            runway_days=row["runway_days"] or 0,
            narrative=row["narrative"] or "",
            anomalies=[
                AnomalyData(
                    category=a["category"],
                    severity=a["severity"],
                    current_amount=a.get("current_amount", 0),
                    baseline_amount=a.get("baseline_amount", 0),
                    deviation_pct=a["deviation_pct"],
                    description=a["description"]
                ) for a in anoms
            ],
            action_items=[] # Advisor data for daily is inside narrative
        ))

    conn.close()
    return result


@router.get("/stats", response_model=BaseResponse)
async def get_stats(
    current_user: dict = Depends(get_current_user),
):
    """Statistik riwayat analisis (diambil dari daily_summaries)."""
    user_id = current_user["id"]
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(*) as total_sessions,
            AVG(health_score) as avg_health,
            MAX(health_score) as best_health,
            MIN(health_score) as worst_health,
            AVG(net_cashflow) as avg_cashflow
        FROM daily_summaries
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if not row or row["total_sessions"] == 0:
        return BaseResponse(
            success=True,
            data={
                "total_sessions": 0,
                "avg_health":     0,
                "best_health":    0,
                "worst_health":   0,
                "avg_cashflow":   0,
            }
        )

    return BaseResponse(
        success=True,
        data={
            "total_sessions": row["total_sessions"],
            "avg_health":     round(row["avg_health"] or 0, 1),
            "best_health":    round(row["best_health"] or 0, 1),
            "worst_health":   round(row["worst_health"] or 0, 1),
            "avg_cashflow":    round(row["avg_cashflow"] or 0, 0),
        }
    )
