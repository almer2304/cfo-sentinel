from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.models.response import BaseResponse
from api.middleware.auth import get_current_user
from core.llm_client import call_llm
from core.prompts import get_conversational_prompt
from core.database import (
    get_connection, save_chat_message,
    get_chat_history, get_chat_sessions,
    delete_chat_session,
)
import uuid
from datetime import datetime

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    session_key: Optional[str] = None


class ChatResponse(BaseModel):
    success: bool
    answer: str
    session_key: str


class ChatHistoryResponse(BaseModel):
    success: bool
    session_key: str
    messages: list[dict]


def _build_financial_context(user_id: int) -> str:
    """
    Ambil konteks keuangan dari daily_summaries (hasil pipeline otomatis).
    Fallback ke analytics lama jika belum ada data pipeline.
    """
    from core.database_new import get_daily_summary, get_cash_balance
    from datetime import datetime, timezone, timedelta

    WIB = timezone(timedelta(hours=7))
    today = datetime.now(WIB).strftime('%Y-%m-%d')

    # Coba dari daily_summaries (pipeline baru)
    summary = get_daily_summary(user_id, today)
    if not summary:
        # Fallback: ambil summary terakhir
        summary = get_daily_summary(user_id)

    if summary:
        cash_balance = get_cash_balance(user_id)
        score = summary.get('health_score', 0)
        status = "BAHAYA" if score < 40 else ("WASPADA" if score < 65 else "AMAN")
        return f"""
Data keuangan bisnis terkini (diperbarui otomatis):
- Skor Kesehatan: {score:.0f}/100 ({status})
- Total Pemasukan Bulan Ini: Rp {summary.get('total_income', 0):,.0f}
- Total Pengeluaran Bulan Ini: Rp {summary.get('total_expense', 0):,.0f}
- Arus Kas Bersih: Rp {summary.get('net_cashflow', 0):,.0f}
- Saldo Kas Saat Ini: Rp {cash_balance:,.0f}
- Uang Habis per Hari: Rp {summary.get('burn_rate_daily', 0):,.0f}
- Perkiraan Uang Bertahan: {summary.get('runway_days', 0):.0f} hari
- Jumlah Anomali: {summary.get('anomaly_count', 0)}
- Analisis AI: {summary.get('agent_narrative', '-')}
- Terakhir diperbarui: {summary.get('processed_at', '-')}
"""

    # Fallback lama ke analytics
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM analytics
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row:
        return "Pengguna baru — belum ada data keuangan. Silakan catat transaksi pertama Anda."

    row = dict(row)
    return f"""
Data keuangan bisnis (dari analisis sebelumnya):
- Skor Kesehatan: {row.get('health_score', 0):.0f}/100
- Total Pemasukan: Rp {row.get('total_income', 0):,.0f}
- Total Pengeluaran: Rp {row.get('total_expense', 0):,.0f}
- Saldo Kas: Rp {row.get('cash_balance', 0):,.0f}
- Uang Habis per Hari: Rp {row.get('burn_rate_daily', 0):,.0f}
- Perkiraan Uang Bertahan: {row.get('runway_days', 0):.0f} hari
"""


@router.post("/ask", response_model=ChatResponse)
async def ask_cfo(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    business_name = current_user.get("business_name", "Bisnis Anda")

    # Gunakan session_key yang ada atau buat baru
    session_key = request.session_key or str(uuid.uuid4())

    # Ambil riwayat percakapan dari database
    history = get_chat_history(user_id, session_key, limit=20)

    # Build financial context
    financial_context = _build_financial_context(user_id)

    # System prompt dengan konteks keuangan
    system_prompt = f"""Kamu adalah CFO Sentinel, asisten keuangan virtual untuk bisnis "{business_name}".

KONTEKS KEUANGAN BISNIS SAAT INI:
{financial_context}

CARA MENJAWAB:
- Gunakan Bahasa Indonesia yang hangat, seperti teman yang pintar
- Sapa dengan nama bisnis jika relevan
- HANYA gunakan angka dari konteks keuangan di atas
- Jika tidak ada data, jujur bilang "belum ada data analisis"
- Berikan saran yang konkret, bukan generik
- Jawaban ringkas tapi bermakna, maksimal 3-4 paragraf
- Jangan gunakan istilah teknis tanpa penjelasan

RIWAYAT PERCAKAPAN INI:
Kamu MEMILIKI ingatan tentang semua yang sudah dibicarakan dalam sesi ini.
Rujuk percakapan sebelumnya jika relevan."""

    # Build messages dengan history
    messages_for_llm = [{"role": "system", "content": system_prompt}]

    # Tambahkan history percakapan
    for msg in history:
        messages_for_llm.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Tambahkan pesan user baru
    messages_for_llm.append({
        "role": "user",
        "content": request.message
    })

    # Simpan pesan user ke database
    save_chat_message(user_id, session_key, "user", request.message)

    try:
        # Panggil LLM dengan full conversation history
        from core.llm_client import _get_client, AGENT_CONFIG
        import time

        config = AGENT_CONFIG.get("advisor", {})
        client = _get_client()

        response = client.chat.completions.create(
            model=config.get("model", "claude-haiku-20240307"),
            messages=messages_for_llm,
            temperature=config.get("temperature", 0.3),
            max_tokens=config.get("max_tokens", 1000),
        )

        answer = response.choices[0].message.content or ""

        # Simpan jawaban AI ke database
        save_chat_message(user_id, session_key, "assistant", answer)

        return ChatResponse(
            success=True,
            answer=answer,
            session_key=session_key,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat gagal: {str(e)}")


@router.get("/history/{session_key}", response_model=ChatHistoryResponse)
async def get_history(
    session_key: str,
    current_user: dict = Depends(get_current_user),
):
    """Ambil riwayat percakapan untuk sesi tertentu."""
    messages = get_chat_history(
        current_user["id"], session_key, limit=100
    )
    return ChatHistoryResponse(
        success=True,
        session_key=session_key,
        messages=messages,
    )


@router.get("/sessions", response_model=BaseResponse)
async def get_sessions(
    current_user: dict = Depends(get_current_user),
):
    """Ambil semua sesi chat user."""
    sessions = get_chat_sessions(current_user["id"])
    return BaseResponse(success=True, data=sessions)


@router.delete("/session/{session_key}", response_model=BaseResponse)
async def delete_session(
    session_key: str,
    current_user: dict = Depends(get_current_user),
):
    """Hapus sesi chat."""
    delete_chat_session(current_user["id"], session_key)
    return BaseResponse(success=True, message="Sesi dihapus.")
