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
)
from core.pipeline import trigger_pipeline

router = APIRouter(prefix="/transactions", tags=["Transactions"])


# ─── Request Models ──────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    type: str = Field(..., pattern="^(income|expense)$",
                      description="income atau expense")
    amount: float = Field(..., gt=0, description="Jumlah dalam rupiah")
    description: str = Field(..., min_length=2, max_length=200)
    category: str = Field(default="Lain-lain", max_length=50)
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
    Simpan satu transaksi (kasir-style).
    Pipeline agent otomatis jalan di background.
    """
    user_id = current_user["id"]

    try:
        tx = save_transaction_simple(
            user_id=user_id,
            type=body.type,
            amount=body.amount,
            description=body.description,
            category=body.category,
            notes=body.notes,
        )

        # Trigger pipeline non-blocking
        trigger_pipeline(tx, user_id)

        return BaseResponse(
            success=True,
            message="Transaksi tersimpan. AI sedang menganalisis...",
            data={
                "transaction_code": tx["transaction_code"],
                "datetime_wib":     tx["datetime_wib"],
                "type":             tx["type"],
                "amount":           tx["amount"],
                "description":      tx["description"],
                "category":         tx["category"],
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
    return BaseResponse(success=True, data=txs)


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
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")

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
        message="Transaksi diperbarui. AI sedang re-analisis...",
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
