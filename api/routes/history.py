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
    Menggabungkan data dari daily_summaries (otomatis) dan backfill jika perlu.
    """
    user_id = current_user["id"]
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Cek tanggal-tanggal yang punya transaksi tapi BELUM punya summary
    cursor.execute("""
        SELECT DISTINCT date_only FROM transactions
        WHERE user_id = ? AND (is_deleted IS NULL OR is_deleted = 0)
        AND date_only NOT IN (SELECT date_only FROM daily_summaries WHERE user_id = ?)
        ORDER BY date_only DESC LIMIT 5
    """, (user_id, user_id))
    missing_dates = [r["date_only"] for r in cursor.fetchall()]

    # 2. Backfill minimal (deterministic) untuk tanggal yang hilang
    if missing_dates:
        from core.database_new import get_financial_summary
        from core.finance_rules import estimate_health_score
        from core.database_new import get_cash_balance
        
        cash_balance = get_cash_balance(user_id)
        
        for d in missing_dates:
            summ = get_financial_summary(user_id, d, d)
            if summ["total_tx"] > 0:
                hs = estimate_health_score(summ, cash_balance)
                cursor.execute("""
                    INSERT OR IGNORE INTO daily_summaries (
                        user_id, date_only, total_income, total_expense,
                        net_cashflow, transaction_count, health_score,
                        agent_narrative
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, d, summ["total_income"] or 0, summ["total_expense"] or 0,
                    (summ["total_income"] or 0) - (summ["total_expense"] or 0),
                    summ["total_tx"], hs, "Analisis otomatis tersedia."
                ))
        conn.commit()

    # 3. Ambil dari daily_summaries (Analisis harian otomatis dari pipeline)
    cursor.execute("""
        SELECT 
            'DAILY-' || date_only as session_id,
            date_only || ' 23:59:59' as created_at,
            health_score, total_income, total_expense, net_cashflow,
            runway_days, transaction_count, agent_narrative as narrative
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
            SELECT category, severity, description, deviation_pct,
                   current_amount, baseline_amount, suggested_action
            FROM transaction_anomalies
            WHERE user_id = ? AND date(detected_at) = ?
        """, (user_id, date_str))
        anoms = cursor.fetchall()

        # Ambil data tambahan untuk build brief (deterministic actions)
        from core.finance_rules import build_dashboard_brief, get_spending_by_category_efficient
        
        tx_count = row["transaction_count"] or 0
        financial = {
            "total_income": row["total_income"] or 0,
            "total_expense": row["total_expense"] or 0,
            "total_tx": tx_count,
            "classified_tx": tx_count,
        }
        spending = get_spending_by_category_efficient(user_id, date_str, date_str)
        brief = build_dashboard_brief(
            financial,
            cash_balance=current_balance,
            health_score=hs,
            runway_days=row["runway_days"] or 0,
            anomalies=anoms,
            spending=spending
        )

        result.append(HistoryItem(
            session_id=row["session_id"],
            created_at=row["created_at"],
            health_score=hs,
            health_status=status,
            total_income=row["total_income"] or 0,
            total_expense=row["total_expense"] or 0,
            net_cashflow=row["net_cashflow"] or 0,
            cash_balance=current_balance, 
            runway_days=row["runway_days"] or 0,
            narrative=row["narrative"] or "",
            anomalies=[
                AnomalyData(
                    category=a["category"],
                    severity=a["severity"],
                    current_amount=a["current_amount"] or 0,
                    baseline_amount=a["baseline_amount"] or 0,
                    deviation_pct=a["deviation_pct"],
                    description=a["description"],
                    suggested_action=a["suggested_action"] or "",
                ) for a in anoms
            ],
            action_items=[
                ActionItemData(
                    priority=i+1,
                    title=item["title"],
                    description=item["description"],
                    urgency=item["urgency"],
                    estimated_impact=item.get("expected_impact", "")
                ) for i, item in enumerate(brief["next_actions"])
            ]
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

    # Pastikan data tersinkronisasi dulu
    cursor.execute("""
        SELECT DISTINCT date_only FROM transactions
        WHERE user_id = ? AND (is_deleted IS NULL OR is_deleted = 0)
        AND date_only NOT IN (SELECT date_only FROM daily_summaries WHERE user_id = ?)
    """, (user_id, user_id))
    missing = cursor.fetchall()
    if missing:
        from core.database_new import get_financial_summary
        from core.finance_rules import estimate_health_score
        from core.database_new import get_cash_balance
        cash_balance = get_cash_balance(user_id)
        for m in missing:
            d = m["date_only"]
            summ = get_financial_summary(user_id, d, d)
            if summ["total_tx"] > 0:
                hs = estimate_health_score(summ, cash_balance)
                cursor.execute("""
                    INSERT OR IGNORE INTO daily_summaries (
                        user_id, date_only, total_income, total_expense,
                        net_cashflow, transaction_count, health_score,
                        agent_narrative
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, d, summ["total_income"] or 0, summ["total_expense"] or 0,
                    (summ["total_income"] or 0) - (summ["total_expense"] or 0),
                    summ["total_tx"], hs, "Analisis otomatis tersedia."
                ))
        conn.commit()

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
