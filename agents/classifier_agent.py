"""
agents/classifier_agent.py — AGENT 1
Klasifikasi akuntansi SAK-ETAP untuk setiap transaksi baru.
Dipanggil otomatis dari background pipeline setelah transaksi disimpan.
"""

import time
from core.llm_client import call_llm_json
from core.database import get_connection, log_agent_step

CLASSIFIER_SYSTEM = """
Kamu adalah Akuntan Profesional Indonesia dengan pengalaman 15 tahun
dalam bidang akuntansi UMKM dan penerapan SAK-ETAP (Standar Akuntansi
Keuangan Entitas Tanpa Akuntabilitas Publik).

TUGASMU:
Klasifikasikan transaksi ke dalam accounting_type yang tepat
berdasarkan prinsip SAK-ETAP.

PRINSIP WAJIB:
- Beli bahan baku/stok untuk dijual = 'asset_purchase' (BUKAN expense langsung)
- Bayar sewa/listrik/gaji/internet = 'operational_expense'
- Penjualan produk/jasa = 'revenue'
- Beli peralatan/mesin = 'asset_purchase'
- Bayar hutang/cicilan = 'debt_payment'
- Terima pembayaran piutang = 'receivable'
- HPP/harga pokok penjualan = 'cogs'

ACCOUNTING TYPES yang tersedia:
revenue, operational_expense, cogs, asset_purchase,
debt_payment, receivable, other

Balas HANYA dengan JSON:
{"accounting_type": "...", "category": "...", "is_recurring": false}
"""


def run_classifier_agent(transaction: dict, user_id: int) -> dict:
    """
    Agent 1: Klasifikasi akuntansi SAK-ETAP untuk satu transaksi.
    Dipanggil otomatis setelah transaksi disimpan.
    EFISIENSI: hanya 1 LLM call per transaksi, input minimal.
    """
    start = time.time()

    user_message = (
        f"Transaksi: {transaction['type']} - "
        f"{transaction['description']} - "
        f"Rp {transaction['amount']:,.0f} - "
        f"Kategori saat ini: {transaction.get('category', 'Lain-lain')}"
    )

    result, meta = call_llm_json(
        agent_name="classifier",
        system_prompt=CLASSIFIER_SYSTEM,
        user_message=user_message,
    )

    duration = int((time.time() - start) * 1000)

    if result:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE transactions
            SET accounting_type   = ?,
                category         = ?,
                is_recurring     = ?,
                agent_classified = 1
            WHERE transaction_code = ? AND user_id = ?
        """, (
            result.get("accounting_type", "other"),
            result.get("category", transaction.get("category", "Lain-lain")),
            1 if result.get("is_recurring") else 0,
            transaction["transaction_code"],
            user_id,
        ))
        conn.commit()
        conn.close()

    log_agent_step(
        session_id=transaction["transaction_code"],
        agent_name="classifier",
        step=1,
        input_summary=f"TX: {transaction['description']} Rp {transaction['amount']:,.0f}",
        reasoning=f"Classified as: {result.get('accounting_type', 'unknown') if result else 'fallback'}",
        output_summary=str(result),
        duration_ms=duration,
        status="success" if result else "fallback",
        user_id=user_id,
    )

    return result or {"accounting_type": "other", "category": transaction.get("category", "Lain-lain")}
