from fastapi import APIRouter, Depends, Query
from api.models.response import HistoryItem, BaseResponse
from api.middleware.auth import get_current_user
from core.database import get_connection

router = APIRouter(prefix="/history", tags=["History"])


@router.get("/list", response_model=list[HistoryItem])
async def get_history(
    limit: int = Query(default=10, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Ambil riwayat analisis user."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            session_id, created_at, health_score,
            total_income, total_expense, net_cashflow,
            cash_balance, runway_days, narrative
        FROM analytics
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (current_user["id"], limit))

    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        hs = row["health_score"] or 0
        if hs >= 65:
            status = "SAFE"
        elif hs >= 50:
            status = "WARNING"
        else:
            status = "DANGER"

        result.append(HistoryItem(
            session_id=row["session_id"] or "",
            created_at=row["created_at"] or "",
            health_score=hs,
            health_status=status,
            total_income=row["total_income"] or 0,
            total_expense=row["total_expense"] or 0,
            net_cashflow=row["net_cashflow"] or 0,
            cash_balance=row["cash_balance"] or 0,
            runway_days=row["runway_days"] or 0,
            narrative=(row["narrative"] or "")[:200],
        ))

    return result


@router.get("/stats", response_model=BaseResponse)
async def get_stats(
    current_user: dict = Depends(get_current_user),
):
    """Statistik ringkasan: tren health score, rata-rata."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            AVG(health_score) as avg_health,
            MAX(health_score) as best_health,
            MIN(health_score) as worst_health,
            AVG(net_cashflow) as avg_cashflow
        FROM analytics
        WHERE user_id = ?
    """, (current_user["id"],))

    row = dict(cursor.fetchone())
    conn.close()

    return BaseResponse(
        success=True,
        data={
            "total_sessions":  row["total"] or 0,
            "avg_health":      round(row["avg_health"] or 0, 1),
            "best_health":     round(row["best_health"] or 0, 1),
            "worst_health":    round(row["worst_health"] or 0, 1),
            "avg_cashflow":    round(row["avg_cashflow"] or 0, 0),
        }
    )
