"""
core/database_new.py
Fungsi-fungsi BARU untuk arsitektur kasir digital.
Diimport dari database.py yang sudah ada.
"""

import random
import string
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def get_now_wib() -> datetime:
    return datetime.now(WIB)


def get_now_wib_str() -> str:
    return get_now_wib().strftime('%Y-%m-%d %H:%M:%S')


def generate_transaction_code() -> str:
    now = get_now_wib()
    date_part = now.strftime('%Y%m%d')
    time_part = now.strftime('%H%M%S')
    rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"TRX-{date_part}-{time_part}-{rand_part}"


def init_new_tables():
    """Buat tabel-tabel baru untuk arsitektur kasir digital."""
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Tambah kolom baru ke transactions jika belum ada
    new_cols = [
        ("transaction_code", "TEXT DEFAULT ''"),
        ("user_id_fk", "INTEGER"),  # alias sementara, user_id sudah ada
        ("datetime_wib", "TEXT DEFAULT ''"),
        ("date_only", "TEXT DEFAULT ''"),
        ("time_only", "TEXT DEFAULT ''"),
        ("accounting_type", "TEXT DEFAULT 'other'"),
        ("notes", "TEXT DEFAULT ''"),
        ("is_corrected", "INTEGER DEFAULT 0"),
        ("original_code", "TEXT DEFAULT ''"),
        ("agent_classified", "INTEGER DEFAULT 0"),
        ("sub_category", "TEXT DEFAULT ''"),
        ("is_business_new", "INTEGER DEFAULT 1"),
        ("is_recurring_new", "INTEGER DEFAULT 0"),
        ("is_deleted", "INTEGER DEFAULT 0"),
        ("raw_input", "TEXT DEFAULT ''"),
        ("debit_account", "TEXT DEFAULT ''"),
        ("credit_account", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in new_cols:
        try:
            cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # already exists

    # Tabel daily_summaries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            date_only       TEXT NOT NULL,
            total_income    REAL DEFAULT 0,
            total_expense   REAL DEFAULT 0,
            net_cashflow    REAL DEFAULT 0,
            operational_expense REAL DEFAULT 0,
            cogs            REAL DEFAULT 0,
            asset_purchase  REAL DEFAULT 0,
            transaction_count INTEGER DEFAULT 0,
            health_score    REAL DEFAULT 0,
            runway_days     REAL DEFAULT 0,
            burn_rate_daily REAL DEFAULT 0,
            anomaly_count   INTEGER DEFAULT 0,
            has_critical_anomaly INTEGER DEFAULT 0,
            agent_narrative TEXT DEFAULT '',
            processed_at    TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(user_id, date_only),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Tabel transaction_anomalies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_anomalies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            transaction_code TEXT DEFAULT '',
            category        TEXT NOT NULL,
            severity        TEXT NOT NULL CHECK(severity IN ('HIGH','MEDIUM','LOW')),
            current_amount  REAL NOT NULL,
            baseline_amount REAL NOT NULL,
            deviation_pct   REAL NOT NULL,
            description     TEXT NOT NULL,
            suggested_action TEXT DEFAULT '',
            is_resolved     INTEGER DEFAULT 0,
            detected_at     TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Index untuk performa
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_user_date
        ON transactions(user_id, date_only)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_user_type
        ON transactions(user_id, type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_code
        ON transactions(transaction_code)
    """)

    conn.commit()
    conn.close()
    print("[OK] New tables and indexes created")


def save_transaction_simple(
    user_id: int,
    raw_input: str,
    notes: str = '',
) -> dict:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    code = generate_transaction_code()
    now_wib = get_now_wib()
    datetime_wib = now_wib.strftime('%Y-%m-%d %H:%M:%S')
    date_only = now_wib.strftime('%Y-%m-%d')
    time_only = now_wib.strftime('%H:%M:%S')

    # Default values sebelum di-analisis agent
    amount = 0.0
    tx_type = 'expense'  # Wajib 'income' atau 'expense' (CHECK constraint DB)
    description = raw_input[:100]  # Gunakan raw_input sebagai deskripsi awal
    category = 'Pending'

    cursor.execute("""
        INSERT INTO transactions (
            transaction_code, user_id, datetime_wib, date_only,
            time_only, type, amount, description, category, notes,
            date, is_business, source, raw_input,
            agent_classified, debit_account, credit_account
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'kasir', ?, 0, 'PENDING', 'PENDING')
    """, (
        code, user_id, datetime_wib, date_only,
        time_only, tx_type, amount, description, category, notes,
        date_only, raw_input
    ))

    conn.commit()
    tx_id = cursor.lastrowid
    conn.close()

    return {
        "id": tx_id,
        "transaction_code": code,
        "user_id": user_id,
        "datetime_wib": datetime_wib,
        "date_only": date_only,
        "time_only": time_only,
        "type": tx_type,
        "amount": amount,
        "description": description,
        "category": category,
        "notes": notes,
        "raw_input": raw_input
    }


def get_transactions_by_user(
    user_id: int,
    date_from: str = None,
    date_to: str = None,
    tx_type: str = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """Ambil transaksi user. Handle transaksi lama (pakai 'date') dan baru (pakai 'date_only')."""
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Pilih kolom yang tersedia — datetime_wib mungkin kosong di transaksi lama
    query = """
        SELECT
            COALESCE(NULLIF(transaction_code,''), 'TRX-LEGACY-' || id) as transaction_code,
            COALESCE(NULLIF(datetime_wib,''), date || ' 00:00:00')      as datetime_wib,
            COALESCE(NULLIF(date_only,''), date)                        as date_only,
            COALESCE(NULLIF(time_only,''), '00:00:00')                  as time_only,
            type, amount, description,
            COALESCE(NULLIF(category,''), 'Lain-lain')                  as category,
            COALESCE(notes, '')                                         as notes,
            COALESCE(accounting_type, 'other')                         as accounting_type,
            COALESCE(is_corrected, 0)                                  as is_corrected,
            COALESCE(is_deleted, 0)                                    as is_deleted
        FROM transactions
        WHERE user_id = ? AND (is_deleted IS NULL OR is_deleted = 0)
    """
    params = [user_id]

    if date_from:
        query += " AND COALESCE(NULLIF(date_only,''), date) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND COALESCE(NULLIF(date_only,''), date) <= ?"
        params.append(date_to)
    if tx_type:
        query += " AND type = ?"
        params.append(tx_type)

    query += " ORDER BY COALESCE(NULLIF(datetime_wib,''), date) DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_financial_summary(user_id: int, date_from: str, date_to: str) -> dict:
    """
    Aggregate query yang handle KEDUA sumber transaksi:
    - Transaksi baru (kasir digital): punya date_only
    - Transaksi lama (import): pakai kolom 'date' sebagai fallback
    """
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Pastikan kolom baru (debit_account/credit_account) dihandle dengan COALESCE
    # untuk data lama yang mungkin belum punya nilai ini.
    cursor.execute("""
        SELECT
            COUNT(*)                                    as total_tx,
            SUM(CASE WHEN type='income'  THEN amount ELSE 0 END) as total_income,
            SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as total_expense,
            SUM(CASE WHEN type='income'  THEN amount
                     WHEN type='expense' THEN -amount ELSE 0 END) as net_cashflow,
            SUM(CASE WHEN accounting_type='operational_expense'
                     THEN amount ELSE 0 END)            as operational_expense,
            SUM(CASE WHEN accounting_type='cogs'
                     THEN amount ELSE 0 END)            as cogs,
            SUM(CASE WHEN accounting_type='asset_purchase'
                     THEN amount ELSE 0 END)            as asset_purchase,
            -- Deteksi Laba Rugi Berbasis Jurnal
            SUM(CASE WHEN (debit_account IN ('Pendapatan Usaha', 'Pendapatan Lain') OR 
                           credit_account IN ('Pendapatan Usaha', 'Pendapatan Lain'))
                     THEN amount ELSE 0 END) as journal_revenue,
            SUM(CASE WHEN (debit_account LIKE 'Beban%' OR credit_account LIKE 'Beban%' OR
                           debit_account = 'HPP (Bahan Baku)' OR credit_account = 'HPP (Bahan Baku)')
                     THEN amount ELSE 0 END) as journal_expense,
            AVG(CASE WHEN type='expense' THEN amount END) as avg_expense_per_tx,
            COUNT(DISTINCT COALESCE(NULLIF(date_only,''), date)) as active_days
        FROM transactions
        WHERE user_id = ?
          AND COALESCE(NULLIF(date_only,''), date) >= ?
          AND COALESCE(NULLIF(date_only,''), date) <= ?
          AND (is_deleted IS NULL OR is_deleted = 0)
    """, (user_id, date_from, date_to))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def get_spending_by_category_efficient(
    user_id: int, date_from: str, date_to: str
) -> list:
    """Aggregate pengeluaran per kategori. Handle transaksi lama & baru."""
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COALESCE(NULLIF(category,''), 'Lain-lain') as category,
            SUM(amount)   as total,
            COUNT(*)      as count,
            AVG(amount)   as avg_per_tx,
            MAX(amount)   as max_tx,
            MIN(amount)   as min_tx
        FROM transactions
        WHERE user_id = ?
          AND type = 'expense'
          AND COALESCE(NULLIF(date_only,''), date) BETWEEN ? AND ?
          AND (is_deleted IS NULL OR is_deleted = 0)
          AND (is_business IS NULL OR is_business = 1)
        GROUP BY COALESCE(NULLIF(category,''), 'Lain-lain')
        ORDER BY total DESC
    """, (user_id, date_from, date_to))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cash_balance(user_id: int) -> float:
    """
    Hitung saldo kas riil menggunakan logika Double-Entry:
    Saldo Kas = Total Debit Akun 'Kas' - Total Kredit Akun 'Kas'
    """
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            SUM(CASE WHEN debit_account = 'Kas' THEN amount ELSE 0 END) as total_debit,
            SUM(CASE WHEN credit_account = 'Kas' THEN amount ELSE 0 END) as total_credit
        FROM transactions
        WHERE user_id = ?
          AND (is_deleted IS NULL OR is_deleted = 0)
          AND debit_account != 'PENDING' 
          AND credit_account != 'PENDING'
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    debit = row["total_debit"] or 0
    credit = row["total_credit"] or 0
    # Pembulatan ke 2 desimal untuk mencegah 'Floating Point Sand' (misal: 0.000000001)
    return round(float(debit - credit), 2)

def get_transaction_by_code(user_id: int, transaction_code: str) -> dict | None:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM transactions
        WHERE transaction_code = ? AND user_id = ?
    """, (transaction_code, user_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_transaction(user_id: int, transaction_code: str, data: dict) -> bool:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    # Reset akun jurnal agar Agent Bookkeeper memproses ulang (Integritas Buku Besar)
    cursor.execute("""
        UPDATE transactions
        SET amount = ?, description = ?, category = ?,
            notes = ?, agent_classified = 0,
            debit_account = '', credit_account = ''
        WHERE transaction_code = ? AND user_id = ?
    """, (
        data.get("amount"), data.get("description"),
        data.get("category"), data.get("notes", ""),
        transaction_code, user_id,
    ))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def soft_delete_transaction(user_id: int, transaction_code: str) -> bool:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE transactions SET is_deleted = 1
        WHERE transaction_code = ? AND user_id = ?
    """, (transaction_code, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_daily_summary(user_id: int, date_only: str = None) -> dict | None:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    if date_only:
        cursor.execute("""
            SELECT * FROM daily_summaries
            WHERE user_id = ? AND date_only = ?
        """, (user_id, date_only))
    else:
        cursor.execute("""
            SELECT * FROM daily_summaries
            WHERE user_id = ?
            ORDER BY date_only DESC LIMIT 1
        """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_health_history(user_id: int, days: int = 30) -> list:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date_only, health_score, net_cashflow,
               total_income, total_expense, agent_narrative
        FROM daily_summaries
        WHERE user_id = ?
        ORDER BY date_only DESC
        LIMIT ?
    """, (user_id, days))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unresolved_anomalies(user_id: int, limit: int = 5) -> list:
    from core.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, severity, description, suggested_action,
               deviation_pct, detected_at
        FROM transaction_anomalies
        WHERE user_id = ? AND is_resolved = 0
          AND detected_at >= date('now', '-30 days')
        ORDER BY
            CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
            detected_at DESC
        LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
