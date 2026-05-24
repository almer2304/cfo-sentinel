"""
api/routes/transactions.py
Route kasir digital — input transaksi satu per satu.
Pipeline agent jalan otomatis di background setelah setiap simpan.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from api.models.response import BaseResponse
from api.middleware.auth import get_current_user
from core.database_new import (
    save_transaction_simple,
    get_transactions_by_user,
    get_transaction_by_code,
    update_transaction,
    soft_delete_transaction,
    get_daily_summary,
    get_financial_summary,
    get_cash_balance,
    get_health_history,
    get_unresolved_anomalies,
)
from core.pipeline import trigger_pipeline
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

router = APIRouter(prefix="/transactions", tags=["Transactions"])


# ─── Request Models ──────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    raw_input: str = Field(..., min_length=2, max_length=500, 
                          description="Input bebas dari user (e.g. 'Beli kopi 20rb')")
    notes: str = Field(default="", max_length=500)


class TransactionUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, min_length=2, max_length=200)
    category: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=500)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("", response_model=BaseResponse)
async def create_transaction(
    body: TransactionCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Simpan satu transaksi (input bebas).
    Pipeline agent otomatis jalan di background untuk memproses jurnal.
    """
    user_id = current_user["id"]

    try:
        tx = save_transaction_simple(
            user_id=user_id,
            raw_input=body.raw_input,
            notes=body.notes,
        )

        # Trigger pipeline non-blocking
        trigger_pipeline(tx, user_id)

        return BaseResponse(
            success=True,
            message="Transaksi tersimpan. AI sedang menganalisis jurnal...",
            data={
                "transaction_code": tx["transaction_code"],
                "datetime_wib":     tx["datetime_wib"],
                "raw_input":        tx["raw_input"],
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal simpan transaksi: {str(e)}")


@router.get("", response_model=BaseResponse)
async def list_transactions(
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    type:      Optional[str] = Query(default=None, description="income|expense"),
    limit:     int = Query(default=50, ge=1, le=200),
    offset:    int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Ambil daftar transaksi dengan filter opsional."""
    user_id = current_user["id"]
    txs = get_transactions_by_user(
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        tx_type=type,
        limit=limit,
        offset=offset,
    )
    
    # Hitung summary cepat
    total_income  = sum(t["amount"] for t in txs if t.get("type") == "income")
    total_expense = sum(t["amount"] for t in txs if t.get("type") == "expense")
    
    return BaseResponse(
        success=True,
        data={
            "items": txs,
            "total_income": total_income,
            "total_expense": total_expense,
            "count": len(txs),
        }
    )


@router.get("/dashboard", response_model=BaseResponse)
async def get_transactions_dashboard(
    current_user: dict = Depends(get_current_user),
):
    """
    Dashboard transaksi: daftar transaksi + health analysis dari pipeline.
    Menggabungkan data v2 transactions + daily_summaries dari background pipeline.
    """
    user_id = current_user["id"]
    now = datetime.now(WIB)
    today = now.strftime('%Y-%m-%d')
    month_start = now.strftime('%Y-%m-01')

    # Ambil transaksi terbaru
    txs = get_transactions_by_user(user_id=user_id, limit=50)
    
    # Ambil daily summary dari pipeline
    summary_today = get_daily_summary(user_id, today)
    
    # Fallback kalau pipeline belum jalan — hitung live dari DB
    if not summary_today:
        financial    = get_financial_summary(user_id, month_start, today)
        cash_balance = get_cash_balance(user_id)
        expense      = financial.get("total_expense", 0) or 0
        income       = financial.get("total_income", 0) or 0
        active_days  = max(financial.get("active_days", 1) or 1, 1)
        burn_day     = expense / active_days
        runway       = round(cash_balance / burn_day) if burn_day > 0 else 999

        summary_today = {
            "health_score":    0,
            "runway_days":     runway,
            "burn_rate_daily": burn_day,
            "total_income":    income,
            "total_expense":   expense,
            "net_cashflow":    income - expense,
            "agent_narrative": "Belum ada analisis hari ini. Tambah transaksi untuk memulai.",
            "anomaly_count":   0,
            "has_critical_anomaly": 0,
        }
    
    cash_balance = get_cash_balance(user_id)
    health_score = summary_today.get("health_score", 0)
    status = (
        "DANGER"  if health_score < 40 else
        "WARNING" if health_score < 65 else
        "SAFE"
    )
    
    # Hitung summary dari transaksi yang ditampilkan
    total_income  = sum(t["amount"] for t in txs if t.get("type") == "income")
    total_expense = sum(t["amount"] for t in txs if t.get("type") == "expense")

    return BaseResponse(
        success=True,
        data={
            "transactions": txs,
            "summary": {
                "total_income":  total_income,
                "total_expense": total_expense,
                "net_cashflow":  total_income - total_expense,
                "count":         len(txs),
            },
            "health": {
                "score":     health_score,
                "status":    status,
                "narrative": summary_today.get("agent_narrative", ""),
                "runway_days":     summary_today.get("runway_days", 0),
                "burn_rate_daily": summary_today.get("burn_rate_daily", 0),
                "anomaly_count":   summary_today.get("anomaly_count", 0),
                "has_critical":    bool(summary_today.get("has_critical_anomaly", 0)),
                "cash_balance":    cash_balance,
            },
            "last_updated": summary_today.get("processed_at", ""),
        }
    )


@router.get("/{transaction_code}", response_model=BaseResponse)
async def get_transaction(
    transaction_code: str,
    current_user: dict = Depends(get_current_user),
):
    """Ambil detail satu transaksi."""
    tx = get_transaction_by_code(current_user["id"], transaction_code)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    return BaseResponse(success=True, data=tx)


@router.patch("/{transaction_code}", response_model=BaseResponse)
async def edit_transaction(
    transaction_code: str,
    body: TransactionUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Edit transaksi yang sudah ada. Re-trigger pipeline setelah edit."""
    user_id = current_user["id"]
    tx = get_transaction_by_code(user_id, transaction_code)
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaksi {transaction_code} tidak ditemukan.")

    # Merge data lama dengan update
    updated_data = {
        "amount":      body.amount      if body.amount      is not None else tx["amount"],
        "description": body.description if body.description is not None else tx["description"],
        "category":    body.category    if body.category    is not None else tx["category"],
        "notes":       body.notes       if body.notes       is not None else tx.get("notes", ""),
    }

    ok = update_transaction(user_id, transaction_code, updated_data)
    if not ok:
        raise HTTPException(status_code=500, detail="Gagal update transaksi.")

    # Re-trigger pipeline supaya health score diupdate
    updated_tx = get_transaction_by_code(user_id, transaction_code)
    if updated_tx:
        trigger_pipeline(updated_tx, user_id)

    return BaseResponse(
        success=True,
        message=f"Transaksi {transaction_code} diperbarui. AI sedang re-analisis...",
        data=updated_tx,
    )


@router.delete("/{transaction_code}", response_model=BaseResponse)
async def delete_transaction(
    transaction_code: str,
    current_user: dict = Depends(get_current_user),
):
    """Soft delete transaksi (tidak dihapus dari DB, hanya ditandai)."""
    user_id = current_user["id"]
    ok = soft_delete_transaction(user_id, transaction_code)
    if not ok:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")

    return BaseResponse(
        success=True,
        message="Transaksi dihapus.",
    )
