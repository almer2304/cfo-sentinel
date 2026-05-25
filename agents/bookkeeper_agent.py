"""
agents/bookkeeper_agent.py — AGENT 1
AI Bookkeeper: Mengubah input bebas menjadi jurnal akuntansi double-entry.
"""

import time
import json
from core.llm_client import call_llm_json
from core.database import get_connection, log_agent_step

BOOKKEEPER_SYSTEM = """
Kamu adalah AI Bookkeeper Expert untuk UMKM Indonesia. Tugasmu adalah menerima input teks bebas
dari pemilik usaha dan mengubahnya menjadi catatan akuntansi yang benar (Double-Entry).

══════════════════════════════════════════════
CHART OF ACCOUNTS (COA) STANDAR:
══════════════════════════════════════════════
1. Aset: Kas, Piutang, Persediaan, Aset Tetap.
2. Kewajiban: Utang Usaha, Utang Bank.
3. Ekuitas: Modal Pemilik, Prive.
4. Pendapatan: Pendapatan Usaha, Pendapatan Lain.
5. Beban: HPP (Bahan Baku), Beban Gaji, Beban Operasional, Beban Sewa, Beban Lain.

══════════════════════════════════════════════
ATURAN JURNAL:
══════════════════════════════════════════════
- Penerimaan uang dari jualan: Debit: Kas, Kredit: Pendapatan Usaha.
- Bayar biaya (listrik, gaji): Debit: Beban [Kategori], Kredit: Kas.
- Beli bahan baku/stok: Debit: Persediaan, Kredit: Kas (atau Utang Usaha jika ngutang).
- Terima bayaran piutang: Debit: Kas, Kredit: Piutang.
- Bayar utang: Debit: Utang Usaha, Kredit: Kas.
- Pemilik ambil uang: Debit: Prive, Kredit: Kas.

══════════════════════════════════════════════
TYPE CLASSIFICATION (accounting_type):
══════════════════════════════════════════════
- revenue: Jika mempengaruhi Pendapatan Usaha.
- operational_expense: Jika mempengaruhi Beban (kecuali HPP).
- cogs: Jika mempengaruhi Beban Pokok (HPP/Bahan Baku).
- asset_purchase: Jika menambah Aset (Persediaan, Aset Tetap).
- debt_payment: Jika mengurangi Kewajiban (Utang).
- receivable: Jika mengurangi Piutang (Uang Masuk dari Piutang).
- other: Selain di atas.

══════════════════════════════════════════════
FORMAT OUTPUT (JSON):
══════════════════════════════════════════════
{
  "amount": <float>,
  "description": "<deskripsi singkat & bersih>",
  "accounting_type": "<revenue|operational_expense|cogs|asset_purchase|debt_payment|receivable|other>",
  "debit_account": "<Nama Akun>",
  "credit_account": "<Nama Akun>",
  "is_recurring": <bool>,
  "is_pnl": <bool, true jika ada akun Pendapatan/Beban terlibat>
}

CONTOH:
Input: "Beli kopi 20rb"
Output: {"amount": 20000, "description": "Beli kopi", "accounting_type": "operational_expense", "debit_account": "Beban Operasional", "credit_account": "Kas", "is_recurring": false, "is_pnl": true}

Input: "Terima bayar hutang pak budi 100rb"
Output: {"amount": 100000, "description": "Pelunasan piutang Pak Budi", "accounting_type": "receivable", "debit_account": "Kas", "credit_account": "Piutang", "is_recurring": false, "is_pnl": false}
"""

def run_bookkeeper_agent(transaction: dict, user_id: int) -> dict:
    """
    Agent 1 (Bookkeeper): Memproses raw_input menjadi satu atau banyak data akuntansi terstruktur.
    """
    start = time.time()
    raw_input = transaction.get("raw_input", transaction.get("description", ""))

    result, meta = call_llm_json(
        agent_name="bookkeeper",
        system_prompt=BOOKKEEPER_SYSTEM,
        user_message=f"Input User: {raw_input}",
    )

    duration = int((time.time() - start) * 1000)
    tx_list = result.get("transactions", []) if result else []

    if tx_list:
        VALID_ACCOUNTS = {
            "Kas", "Piutang", "Persediaan", "Aset Tetap",
            "Utang Usaha", "Utang Bank", "Modal Pemilik", "Prive",
            "Pendapatan Usaha", "Pendapatan Lain",
            "HPP (Bahan Baku)", "Beban Gaji", "Beban Operasional", "Beban Sewa", "Beban Lain"
        }
        
        def normalize_account(acc):
            if not acc: return "Lain-lain"
            acc_clean = str(acc).strip()
            if "Kas" in acc_clean: return "Kas"
            if "Piutang" in acc_clean: return "Piutang"
            if "Utang" in acc_clean: return "Utang Usaha"
            if "Modal" in acc_clean: return "Modal Pemilik"
            if acc_clean not in VALID_ACCOUNTS: return "Beban Lain"
            return acc_clean

        conn = get_connection()
        cursor = conn.cursor()

        # Update transaksi PERTAMA (yang sudah ada ID-nya)
        first = tx_list[0]
        cursor.execute("""
            UPDATE transactions
            SET amount = ?, description = ?, accounting_type = ?,
                debit_account = ?, credit_account = ?, is_recurring = ?,
                agent_classified = 1, type = ?
            WHERE transaction_code = ? AND user_id = ?
        """, (
            first.get("amount", 0), first.get("description", raw_input),
            first.get("accounting_type", "other"),
            normalize_account(first.get("debit_account")),
            normalize_account(first.get("credit_account")),
            1 if first.get("is_recurring") else 0,
            "income" if normalize_account(first.get("debit_account")) == "Kas" else "expense",
            transaction["transaction_code"], user_id
        ))

        # Jika ada transaksi tambahan (SPLIT), insert sebagai row baru
        if len(tx_list) > 1:
            from core.database_new import generate_transaction_code
            for extra in tx_list[1:]:
                new_code = generate_transaction_code()
                cursor.execute("""
                    INSERT INTO transactions (
                        transaction_code, user_id, datetime_wib, date_only,
                        time_only, type, amount, description, category,
                        accounting_type, debit_account, credit_account,
                        agent_classified, is_business, source, raw_input, date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 'split_ai', ?, ?)
                """, (
                    new_code, user_id, transaction.get("datetime_wib"),
                    transaction.get("date_only"), transaction.get("time_only"),
                    "income" if normalize_account(extra.get("debit_account")) == "Kas" else "expense",
                    extra.get("amount", 0), extra.get("description", raw_input),
                    "Split", extra.get("accounting_type", "other"),
                    normalize_account(extra.get("debit_account")),
                    normalize_account(extra.get("credit_account")),
                    transaction.get("raw_input", ""), transaction.get("date_only")
                ))

        conn.commit()
        conn.close()

    log_agent_step(
        session_id=transaction["transaction_code"],
        agent_name="bookkeeper",
        step=1,
        input_summary=f"Raw: {raw_input}",
        reasoning=f"Splits: {len(tx_list)} entries created.",
        output_summary=str(result),
        duration_ms=duration,
        status="success" if result else "fallback",
        user_id=user_id,
    )

    return result or {"transactions": []}

