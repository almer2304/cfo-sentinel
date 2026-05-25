"""
agents/bookkeeper_agent.py - Agent 1

AI Bookkeeper yang dijaga rules engine deterministik. Targetnya bukan sekadar
menebak kategori, tetapi membuat jurnal dasar yang cukup aman untuk dashboard
kas, laba-rugi, dan audit transaksi UMKM.
"""

import time

from core.database import get_connection, log_agent_step
from core.finance_rules import classify_raw_transaction


VALID_ACCOUNTS = {
    "Kas", "Piutang", "Persediaan", "Aset Tetap",
    "Utang Usaha", "Utang Bank", "Modal Pemilik", "Prive",
    "Pendapatan Usaha", "Pendapatan Lain",
    "HPP (Bahan Baku)", "Beban Gaji", "Beban Operasional",
    "Beban Sewa", "Beban Pemasaran", "Beban Lain",
}


def normalize_account(account: str) -> str:
    if not account:
        return "Beban Lain"
    acc = str(account).strip()
    if acc in VALID_ACCOUNTS:
        return acc
    if "kas" in acc.lower():
        return "Kas"
    if "piutang" in acc.lower():
        return "Piutang"
    if "persediaan" in acc.lower() or "stok" in acc.lower():
        return "Persediaan"
    if "aset" in acc.lower():
        return "Aset Tetap"
    if "utang" in acc.lower() or "hutang" in acc.lower():
        return "Utang Usaha"
    if "pendapatan" in acc.lower() or "penjualan" in acc.lower():
        return "Pendapatan Usaha"
    if "hpp" in acc.lower() or "bahan" in acc.lower():
        return "HPP (Bahan Baku)"
    if "gaji" in acc.lower():
        return "Beban Gaji"
    if "sewa" in acc.lower():
        return "Beban Sewa"
    if "marketing" in acc.lower() or "pemasaran" in acc.lower() or "iklan" in acc.lower():
        return "Beban Pemasaran"
    if "beban" in acc.lower():
        return "Beban Operasional"
    return "Beban Lain"


def _update_first_transaction(cursor, transaction: dict, entry: dict, user_id: int):
    cursor.execute("""
        UPDATE transactions
        SET amount = ?, description = ?, category = ?, sub_category = ?,
            accounting_type = ?, debit_account = ?, credit_account = ?,
            is_recurring = ?, is_business = ?, confidence = ?,
            agent_classified = 1, type = ?, raw_input = ?
        WHERE transaction_code = ? AND user_id = ?
    """, (
        entry.get("amount", 0),
        entry.get("description", transaction.get("raw_input", "")),
        entry.get("category", "Lain-lain"),
        entry.get("sub_category", ""),
        entry.get("accounting_type", "other"),
        normalize_account(entry.get("debit_account", "")),
        normalize_account(entry.get("credit_account", "")),
        1 if entry.get("is_recurring") else 0,
        1 if entry.get("is_business", True) else 0,
        entry.get("confidence", 0.0),
        entry.get("type", "expense"),
        transaction.get("raw_input") or transaction.get("description", ""),
        transaction["transaction_code"],
        user_id,
    ))


def _insert_split_transaction(cursor, transaction: dict, entry: dict, user_id: int):
    from core.database_new import generate_transaction_code

    new_code = generate_transaction_code()
    cursor.execute("""
        INSERT INTO transactions (
            transaction_code, user_id, datetime_wib, date_only, time_only,
            type, amount, description, category, sub_category,
            accounting_type, debit_account, credit_account,
            is_recurring, is_business, confidence,
            agent_classified, source, raw_input, notes, date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'split_ai', ?, ?, ?)
    """, (
        new_code,
        user_id,
        transaction.get("datetime_wib", ""),
        transaction.get("date_only", transaction.get("date", "")),
        transaction.get("time_only", ""),
        entry.get("type", "expense"),
        entry.get("amount", 0),
        entry.get("description", transaction.get("raw_input", "")),
        entry.get("category", "Lain-lain"),
        entry.get("sub_category", ""),
        entry.get("accounting_type", "other"),
        normalize_account(entry.get("debit_account", "")),
        normalize_account(entry.get("credit_account", "")),
        1 if entry.get("is_recurring") else 0,
        1 if entry.get("is_business", True) else 0,
        entry.get("confidence", 0.0),
        transaction.get("raw_input") or transaction.get("description", ""),
        transaction.get("notes", ""),
        transaction.get("date_only", transaction.get("date", "")),
    ))


def run_bookkeeper_agent(transaction: dict, user_id: int) -> dict:
    """
    Agent 1: raw input -> jurnal double-entry sederhana.

    Rules engine menjadi sumber utama agar transaksi tetap bisa diproses tanpa
    API key LLM. Jika nominal tidak ditemukan, row dibiarkan Pending.
    """
    start = time.time()
    raw_input = transaction.get("raw_input") or transaction.get("description", "")

    result = classify_raw_transaction(raw_input)
    tx_list = result.get("transactions", [])

    if tx_list:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            _update_first_transaction(cursor, transaction, tx_list[0], user_id)
            for extra in tx_list[1:]:
                _insert_split_transaction(cursor, transaction, extra, user_id)
            conn.commit()
        finally:
            conn.close()

    duration = int((time.time() - start) * 1000)
    status = "success" if tx_list else "fallback"
    primary = tx_list[0] if tx_list else {}

    log_agent_step(
        session_id=transaction["transaction_code"],
        agent_name="bookkeeper",
        step=1,
        input_summary=f"Raw: {raw_input}",
        reasoning=result.get("reasoning", ""),
        output_summary=(
            f"{len(tx_list)} jurnal | "
            f"{primary.get('category', 'Pending')} | "
            f"Rp {primary.get('amount', 0):,.0f}"
        ),
        duration_ms=duration,
        status=status,
        user_id=user_id,
    )

    return {
        **result,
        "accounting_type": primary.get("accounting_type", "pending"),
        "category": primary.get("category", "Pending"),
        "status": status,
    }
