"""
api/routes/chat.py
Chat Agent — CFO Virtual yang membaca data REAL-TIME dari transactions.

PRINSIP:
- JANGAN inject raw data ke prompt
- Query aggregate dulu, inject hasilnya ke prompt
- Deteksi intent → query data yang relevan saja
- Total konteks < 500 token

TERMINOLOGI BENAR (sesuai ayah user yang akuntan):
  Pemasukan = Penjualan (income)
  Pengeluaran = Pembelian (expense)
  → Keduanya adalah istilah yang sama dari sudut berbeda.
"""

import re
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

from api.models.response import BaseResponse
from api.middleware.auth import get_current_user
from core.database import (
    get_connection, save_chat_message,
    get_chat_history, get_chat_sessions,
    delete_chat_session,
)
from core.database_new import (
    get_financial_summary,
    get_cash_balance,
    get_spending_by_category_efficient,
)

WIB = timezone(timedelta(hours=7))
router = APIRouter(prefix="/chat", tags=["Chat"])


# ─── Models ──────────────────────────────────────────────────────────────────

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


# ─── Intent Detection (zero LLM cost) ────────────────────────────────────────

def _detect_intent(message: str) -> list[str]:
    """
    Deteksi apa yang ditanyakan user.
    Pure logic — 0 token cost.
    """
    msg = message.lower()
    intents = []

    if any(w in msg for w in ["untung", "laba", "rugi", "profit", "margin", "selisih"]):
        intents.append("profitability")
    if any(w in msg for w in ["keluar", "pengeluaran", "pembelian", "beli", "biaya", "bayar"]):
        intents.append("expense")
    if any(w in msg for w in ["masuk", "pemasukan", "penjualan", "jual", "pendapatan", "omzet"]):
        intents.append("income")
    if any(w in msg for w in ["saldo", "kas", "tahan", "bertahan", "sisa", "uang"]):
        intents.append("balance")
    if any(w in msg for w in ["anomali", "tidak biasa", "aneh", "lonjak", "curiga"]):
        intents.append("anomaly")
    if any(w in msg for w in ["trx-", "transaksi", "catat", "riwayat", "daftar", "list"]):
        intents.append("transaction")
    if any(w in msg for w in ["sehat", "health", "skor", "kondisi", "bahaya", "aman"]):
        intents.append("health")
    if any(w in msg for w in ["kategori", "terbesar", "terbanyak", "paling boros"]):
        intents.append("category")

    if not intents:
        intents = ["summary"]

    return intents


# ─── Smart Context Builder ────────────────────────────────────────────────────

def _build_context(user_id: int, user: dict, intents: list[str], message: str) -> str:
    """
    Query HANYA data yang relevan dengan pertanyaan user.
    Inject hasil aggregate — bukan raw data.
    Target: < 500 token injected.

    CATATAN TERMINOLOGI:
    - "Pemasukan" dan "Penjualan" adalah hal yang SAMA (income/revenue)
    - "Pengeluaran" dan "Pembelian" adalah hal yang SAMA (expense)
    - Terminologi ini benar secara akuntansi (prinsip ayah user)
    """
    now = datetime.now(WIB)
    today = now.strftime('%Y-%m-%d')
    month_start = now.strftime('%Y-%m-01')

    parts = [
        f"Nama Bisnis: {user.get('business_name', 'Bisnis')}",
        f"Jenis Bisnis: {user.get('business_type', 'umum')}",
        f"Tanggal sekarang: {today} WIB",
        "",
        "CATATAN TERMINOLOGI:",
        "- Pemasukan kas = uang yang benar-benar masuk ke Kas",
        "- Pengeluaran kas = uang yang benar-benar keluar dari Kas",
        "- Penjualan/Pendapatan dan Beban dihitung dari jurnal, bukan sekadar arus kas",
        "- Saldo Kas dihitung dari akun Kas: debit Kas - kredit Kas",
    ]

    # Selalu sertakan summary ringkas bulan ini dan HARI INI
    summary = get_financial_summary(user_id, month_start, today)
    summary_today = get_financial_summary(user_id, today, today)
    cash_balance = get_cash_balance(user_id)

    income  = summary.get("total_income", 0) or 0
    expense = summary.get("total_expense", 0) or 0
    net     = income - expense
    tx_count = summary.get("total_tx", 0) or 0
    active_days = max(summary.get("active_days", 1) or 1, 1)
    burn_day = expense / active_days
    runway = round(cash_balance / burn_day) if burn_day > 0 else 999

    income_today = summary_today.get("total_income", 0) or 0
    expense_today = summary_today.get("total_expense", 0) or 0
    tx_count_today = summary_today.get("total_tx", 0) or 0

    parts.append(
        f"\n=== RINGKASAN HARI INI ({today}) ==="
        f"\n- Pemasukan/Penjualan Hari Ini: Rp {income_today:,.0f}"
        f"\n- Pengeluaran/Pembelian Hari Ini: Rp {expense_today:,.0f}"
        f"\n- Jumlah Transaksi Hari Ini: {tx_count_today}"
        f"\n"
        f"\n=== RINGKASAN BULAN INI ({month_start} s/d {today}) ==="
        f"\n- Total Pemasukan/Penjualan (income): Rp {income:,.0f}"
        f"\n- Total Pengeluaran/Pembelian (expense): Rp {expense:,.0f}"
        f"\n- Arus Kas Bersih: Rp {net:,.0f}"
        f"\n- Saldo Kas (semua waktu): Rp {cash_balance:,.0f}"
        f"\n- Jumlah Transaksi Bulan Ini: {tx_count}"
        f"\n- Rata-rata pengeluaran per hari: Rp {burn_day:,.0f}"
        f"\n- Perkiraan bertahan: {runway} hari"
    )

    # Query tambahan sesuai intent
    if "profitability" in intents:
        ops_exp = summary.get("operational_expense", 0) or 0
        cogs    = summary.get("cogs", 0) or 0
        asset   = summary.get("asset_purchase", 0) or 0
        revenue = summary.get("journal_revenue", 0) or 0
        actual_expense = ops_exp + cogs
        profit  = revenue - actual_expense
        margin  = (profit / revenue * 100) if revenue > 0 else 0
        parts.append(
            f"\n=== ANALISIS LABA-RUGI ==="
            f"\n- Pendapatan/Jurnal Penjualan: Rp {revenue:,.0f}"
            f"\n- Beban Operasional (sewa/listrik/gaji): Rp {ops_exp:,.0f}"
            f"\n- HPP/COGS: Rp {cogs:,.0f}"
            f"\n- Total Beban Aktual: Rp {actual_expense:,.0f}"
            f"\n- Pembelian Aset/Stok: Rp {asset:,.0f} (ini BUKAN beban langsung)"
            f"\n- Laba Operasional Estimasi: Rp {profit:,.0f}"
            f"\n- Margin: {margin:.1f}%"
        )

    if "expense" in intents or "category" in intents:
        categories = get_spending_by_category_efficient(user_id, month_start, today)
        if categories:
            lines = ["\n=== PENGELUARAN/PEMBELIAN PER KATEGORI ==="]
            for c in categories[:8]:
                lines.append(
                    f"- {c['category']}: Rp {c['total']:,.0f} "
                    f"({c['count']} transaksi, rata-rata Rp {c.get('avg_per_tx', 0):,.0f})"
                )
            parts.append("\n".join(lines))

    if "anomaly" in intents:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category, severity, description, suggested_action, deviation_pct
            FROM transaction_anomalies
            WHERE user_id = ?
              AND detected_at >= date('now', '-30 days')
              AND is_resolved = 0
            ORDER BY
                CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                detected_at DESC
            LIMIT 5
        """, (user_id,))
        anomalies = cursor.fetchall()
        conn.close()
        if anomalies:
            lines = ["\n=== ANOMALI TERDETEKSI (30 hari terakhir) ==="]
            for a in anomalies:
                lines.append(
                    f"- [{a['severity']}] {a['category']}: {a['description']} "
                    f"(deviasi {a['deviation_pct']:.0f}%)"
                )
            parts.append("\n".join(lines))

    if "transaction" in intents:
        # Cek kode TRX spesifik dalam pesan
        trx_codes = re.findall(r'TRX-\d{8}-\d{6}-[A-Z0-9]{4}', message.upper())
        if trx_codes:
            conn = get_connection()
            cursor = conn.cursor()
            for code in trx_codes[:3]:
                cursor.execute("""
                    SELECT transaction_code, datetime_wib, type,
                           amount, description, category, accounting_type, notes
                    FROM transactions
                    WHERE transaction_code = ? AND user_id = ?
                """, (code, user_id))
                tx = cursor.fetchone()
                if tx:
                    tx_type_label = "Pemasukan/Penjualan" if tx["type"] == "income" else "Pengeluaran/Pembelian"
                    parts.append(
                        f"\n=== DETAIL TRANSAKSI {code} ==="
                        f"\n- Waktu: {tx['datetime_wib']} WIB"
                        f"\n- Tipe: {tx_type_label}"
                        f"\n- Jumlah: Rp {tx['amount']:,.0f}"
                        f"\n- Deskripsi: {tx['description']}"
                        f"\n- Kategori: {tx['category']}"
                        f"\n- Klasifikasi Akuntansi: {tx['accounting_type']}"
                        f"\n- Catatan: {tx['notes'] or '-'}"
                    )
            conn.close()
        else:
            # Tampilkan 10 transaksi terakhir sebagai ringkasan (bukan raw dump)
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT transaction_code, datetime_wib, type, amount, description, category
                FROM transactions
                WHERE user_id = ? AND (is_deleted IS NULL OR is_deleted = 0)
                ORDER BY datetime_wib DESC
                LIMIT 10
            """, (user_id,))
            rows = cursor.fetchall()
            conn.close()
            if rows:
                lines = ["\n=== 10 TRANSAKSI TERAKHIR ==="]
                for r in rows:
                    sign = "+" if r["type"] == "income" else "-"
                    tipe = "Pemasukan" if r["type"] == "income" else "Pengeluaran"
                    lines.append(
                        f"[{r['transaction_code']}] {r['datetime_wib'][:10]} "
                        f"{tipe} {sign}Rp {r['amount']:,.0f} — {r['description']} ({r['category']})"
                    )
                parts.append("\n".join(lines))
                parts.append(
                    f"\nTotal semua waktu: {tx_count} transaksi. "
                    f"Sebutkan kode TRX-... untuk detail spesifik."
                )

    if "health" in intents:
        score = 0
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT health_score, agent_narrative, processed_at
                FROM daily_summaries
                WHERE user_id = ?
                ORDER BY date_only DESC LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                score = row["health_score"] or 0
                status = "BAHAYA 🔴" if score < 40 else ("WASPADA ⚠️" if score < 65 else "SEHAT ✅")
                parts.append(
                    f"\n=== KESEHATAN BISNIS ==="
                    f"\n- Skor: {score:.0f}/100 ({status})"
                    f"\n- Analisis AI: {row['agent_narrative']}"
                    f"\n- Diperbarui: {row['processed_at']}"
                )
        except Exception:
            pass

    return "\n".join(parts)


# ─── Main Chat Endpoint ───────────────────────────────────────────────────────

CHAT_SYSTEM = """
Kamu adalah CFO Virtual — teman bisnis yang sangat paham keuangan dan
selalu memberikan saran yang praktis berdasarkan data nyata.

CARA MENJAWAB:
- Bahasa Indonesia sehari-hari yang hangat, tidak formal
- HANYA gunakan angka dari DATA KEUANGAN yang diberikan — JANGAN mengarang
- Jawaban ringkas tapi bermakna (maksimal 3 paragraf)
- Selalu akhiri dengan SATU saran konkret yang bisa dilakukan hari ini
- Jika user tanya tentang transaksi spesifik, kutip datanya

TERMINOLOGI YANG BENAR:
- Pemasukan kas adalah uang yang benar-benar masuk ke akun Kas.
- Pengeluaran kas adalah uang yang benar-benar keluar dari akun Kas.
- Penjualan/Pendapatan dan Beban memakai jurnal akuntansi.
- Saldo Kas = debit Kas - kredit Kas. Jangan sebut ini laba.

JIKA BELUM ADA DATA:
Katakan jujur bahwa belum ada transaksi tercatat, dan minta user
mulai catat transaksi pertama lewat tombol "Catat" di bawah layar.
"""

@router.post("/ask", response_model=ChatResponse)
async def ask_cfo(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Tanya CFO Virtual. Konteks dibangun dinamis berdasarkan intent.
    """
    user_id = current_user["id"]
    session_key = request.session_key or str(uuid.uuid4())

    try:
        # Step 1: Deteksi intent — 0 token cost
        intents = _detect_intent(request.message)

        # Step 2: Build context real-time dari DB
        context = _build_context(user_id, current_user, intents, request.message)

        # Step 3: Ambil history percakapan
        history_rows = get_chat_history(user_id, session_key, limit=10)
        history_msgs = []
        for h in history_rows:
            history_msgs.append({"role": h["role"], "content": h["content"]})

        # Step 4: Simpan pesan user (dalam try agar safe)
        save_chat_message(user_id, session_key, "user", request.message)

        # Step 5: Panggil LLM menggunakan wrapper standar
        from core.llm_client import call_llm
        from core.prompts import get_conversational_prompt
        
        system_prompt = get_conversational_prompt(context)
        
        answer, meta = call_llm(
            agent_name="advisor", # Gunakan config advisor agar lebih cerdas
            system_prompt=system_prompt,
            user_message=request.message,
            conversation_history=history_msgs,
            response_format="text"
        )

        if not answer:
            answer = "Maaf, saya sedang sulit berpikir. Bisa ulangi pertanyaannya?"

        # Step 6: Simpan jawaban assistant
        save_chat_message(user_id, session_key, "assistant", answer)

        return ChatResponse(
            success=True, 
            answer=answer, 
            session_key=session_key
        )

    except Exception as e:
        print(f"[CHAT ERROR] {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Chat gagal diproses: {str(e)}"
        )


# ─── History & Session Endpoints ─────────────────────────────────────────────

@router.get("/history/{session_key}", response_model=ChatHistoryResponse)
async def get_history(
    session_key: str,
    current_user: dict = Depends(get_current_user),
):
    messages = get_chat_history(current_user["id"], session_key, limit=100)
    return ChatHistoryResponse(success=True, session_key=session_key, messages=messages)


@router.get("/sessions", response_model=BaseResponse)
async def get_sessions(current_user: dict = Depends(get_current_user)):
    sessions = get_chat_sessions(current_user["id"])
    return BaseResponse(success=True, data=sessions)


@router.delete("/session/{session_key}", response_model=BaseResponse)
async def delete_session(
    session_key: str,
    current_user: dict = Depends(get_current_user),
):
    delete_chat_session(current_user["id"], session_key)
    return BaseResponse(success=True, message="Sesi dihapus.")
