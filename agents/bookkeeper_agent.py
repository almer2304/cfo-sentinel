"""
agents/bookkeeper_agent.py — AGENT 1
AI Bookkeeper: Mengubah input bebas menjadi jurnal akuntansi double-entry.
"""

import time
import json
from core.llm_client import call_llm_json
from core.database import get_connection, log_agent_step
from core.prompts import BOOKKEEPER_SYSTEM

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

