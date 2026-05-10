"""
core/database.py
CFO Sentinel — Database Layer
Semua interaksi dengan SQLite ada di sini.
Tidak ada file lain yang boleh langsung akses SQLite
kecuali melalui fungsi-fungsi di file ini.
"""

import sqlite3
import os
import bcrypt
import secrets
from datetime import datetime, timedelta
from pathlib import Path

# Path ke file database
DB_PATH = Path(__file__).parent.parent / "data" / "cfo_sentinel.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_connection() -> sqlite3.Connection:
    """
    Buat koneksi ke SQLite.
    row_factory = sqlite3.Row agar hasil query bisa diakses
    seperti dictionary (row["column_name"]).
    """
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    """
    Inisialisasi semua tabel.
    Dipanggil sekali saat aplikasi pertama kali dijalankan.
    Aman dipanggil berulang (IF NOT EXISTS).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ── TABEL 0: USERS ────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name   TEXT NOT NULL,
            email           TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            business_type   TEXT DEFAULT 'general',
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            last_login      TEXT,
            total_sessions  INTEGER DEFAULT 0
        )
    """)

    # ── TABEL 1: TRANSACTIONS ──────────────────────────────────────
    # Menyimpan semua transaksi yang sudah di-parse oleh Parser Agent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            amount          REAL NOT NULL,
            type            TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            description     TEXT NOT NULL,
            category        TEXT,
            sub_category    TEXT,
            is_recurring    INTEGER DEFAULT 0,  -- 0=false, 1=true
            is_business     INTEGER DEFAULT 1,  -- 0=personal, 1=business
            confidence      REAL DEFAULT 1.0,   -- confidence score 0.0-1.0
            source          TEXT DEFAULT 'manual',  -- 'manual', 'csv', 'seed'
            session_id      TEXT,
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 2: ANALYTICS ─────────────────────────────────────────
    # Hasil kalkulasi dari Financial Analyst Agent
    # Satu row per session analisis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id              TEXT NOT NULL,
            period_start            TEXT NOT NULL,
            period_end              TEXT NOT NULL,
            total_income            REAL DEFAULT 0,
            total_expense           REAL DEFAULT 0,
            net_cashflow            REAL DEFAULT 0,
            cash_balance            REAL DEFAULT 0,
            burn_rate_daily         REAL DEFAULT 0,
            burn_rate_monthly       REAL DEFAULT 0,
            gross_margin            REAL DEFAULT 0,
            runway_days             REAL DEFAULT 0,
            revenue_consistency     REAL DEFAULT 0,  -- 0.0-1.0
            health_score            REAL DEFAULT 0,  -- 0-100
            health_score_prev       REAL DEFAULT 0,  -- bulan lalu
            health_score_industry   REAL DEFAULT 0,  -- rata-rata industri
            health_score_threshold  REAL DEFAULT 50, -- danger threshold
            forecast_30d            TEXT,            -- JSON array
            narrative               TEXT,
            business_type           TEXT DEFAULT 'general',
            created_at              TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 3: ANOMALIES ─────────────────────────────────────────
    # Anomali yang ditemukan oleh Anomaly Detection Agent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomalies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            category        TEXT NOT NULL,
            severity        TEXT NOT NULL CHECK(severity IN ('HIGH', 'MEDIUM', 'LOW')),
            current_amount  REAL NOT NULL,
            baseline_amount REAL NOT NULL,
            deviation_pct   REAL NOT NULL,   -- persentase deviasi dari baseline
            description     TEXT NOT NULL,
            is_validated    INTEGER DEFAULT 0,  -- sudah divalidasi Critic Pattern?
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 4: RECOMMENDATIONS ───────────────────────────────────
    # Rekomendasi dari Strategic Advisor Agent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            priority        INTEGER NOT NULL,  -- 1=highest, 2, 3, dst
            title           TEXT NOT NULL,
            description     TEXT NOT NULL,
            impact          TEXT,              -- estimasi dampak
            urgency         TEXT CHECK(urgency IN ('IMMEDIATE', 'THIS_WEEK', 'THIS_MONTH')),
            category        TEXT,
            early_warning   TEXT,              -- peringatan dini jika ada
            confidence_min  REAL,              -- confidence range minimum
            confidence_max  REAL,              -- confidence range maximum
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 5: MONTHLY SNAPSHOTS ─────────────────────────────────
    # Ringkasan keuangan per bulan untuk Persistent Memory Layer
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            year_month      TEXT NOT NULL UNIQUE,  -- format: "2026-04"
            total_income    REAL DEFAULT 0,
            total_expense   REAL DEFAULT 0,
            net_cashflow    REAL DEFAULT 0,
            health_score    REAL DEFAULT 0,
            burn_rate       REAL DEFAULT 0,
            runway_days     REAL DEFAULT 0,
            business_type   TEXT DEFAULT 'general',
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 6: SPENDING BASELINES ────────────────────────────────
    # Rata-rata pengeluaran per kategori (untuk Anomaly Detection)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spending_baselines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            category        TEXT NOT NULL,
            business_type   TEXT NOT NULL,
            avg_monthly     REAL DEFAULT 0,    -- rata-rata bulanan
            std_deviation   REAL DEFAULT 0,    -- standar deviasi
            sample_months   INTEGER DEFAULT 0, -- jumlah bulan data
            updated_at      TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(category, business_type)
        )
    """)

    # ── TABEL 7: AGENT LOGS ────────────────────────────────────────
    # Reasoning log setiap agent (untuk Reasoning Log UI)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            agent_name      TEXT NOT NULL,
            step            INTEGER NOT NULL,
            input_summary   TEXT,
            reasoning       TEXT,
            output_summary  TEXT,
            duration_ms     INTEGER,
            status          TEXT DEFAULT 'success',  -- 'success', 'error', 'fallback'
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 8: SCENARIOS ─────────────────────────────────────────
    # Hasil simulasi dari Scenario Agent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          TEXT NOT NULL,
            scenario_type       TEXT NOT NULL,   -- 'revenue_drop', 'cost_increase', dll
            parameter_name      TEXT NOT NULL,   -- 'revenue', 'marketing_cost', dll
            parameter_change    REAL NOT NULL,   -- persentase perubahan (-20 = turun 20%)
            new_runway_days     REAL,
            new_health_score    REAL,
            breakeven_day       INTEGER,         -- hari ke berapa titik kritis
            cuttable_costs      TEXT,            -- JSON: biaya yang bisa dipotong
            fixed_costs         TEXT,            -- JSON: biaya yang tidak bisa dipotong
            mitigation_steps    TEXT,            -- narasi langkah mitigasi
            confidence_range    TEXT,            -- JSON: {min, max, expected}
            created_at          TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # ── TABEL 9: SESSION TOKENS ────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            token       TEXT NOT NULL UNIQUE,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            expires_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

    # Migrasi: tambah kolom user_id ke semua tabel yang sudah ada
    migrate_add_user_id()

    print("[OK] Database initialized successfully")
    print(f"   Location: {DB_PATH}")


def migrate_add_user_id():
    """
    Tambah kolom user_id ke semua tabel yang sudah ada.
    Aman dijalankan berulang kali (cek dulu sebelum alter).
    """
    conn = get_connection()
    cursor = conn.cursor()

    tables = [
        "transactions", "analytics", "anomalies",
        "recommendations", "monthly_snapshots",
        "spending_baselines", "agent_logs", "scenarios",
    ]

    for table in tables:
        try:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"
            )
            print(f"  [OK] Added user_id to {table}")
        except Exception:
            pass  # Kolom sudah ada — skip

    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Users
# ══════════════════════════════════════════════════════════════════

def create_user(business_name: str, email: str, password: str,
                business_type: str = "general") -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?",
                   (email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        return None
    password_hash = bcrypt.hashpw(
        password.encode('utf-8'), bcrypt.gensalt()
    ).decode('utf-8')
    cursor.execute("""
        INSERT INTO users (business_name, email, password_hash, business_type)
        VALUES (?, ?, ?, ?)
    """, (business_name.strip(), email.lower().strip(),
          password_hash, business_type))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": user_id, "business_name": business_name.strip(),
            "email": email.lower().strip(), "business_type": business_type}


def verify_login(email: str, password: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?",
                   (email.lower().strip(),))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return None
    user_dict = dict(user)
    if not bcrypt.checkpw(password.encode('utf-8'),
                          user_dict["password_hash"].encode('utf-8')):
        conn.close()
        return None
    cursor.execute("""
        UPDATE users SET last_login = datetime('now', 'localtime'),
            total_sessions = total_sessions + 1 WHERE id = ?
    """, (user_dict["id"],))
    conn.commit()
    conn.close()
    user_dict.pop("password_hash", None)
    return user_dict


def get_user_stats(user_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as total FROM analytics WHERE user_id = ?",
        (user_id,))
    total_sessions = cursor.fetchone()["total"]
    cursor.execute("""
        SELECT health_score, created_at FROM analytics
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 3
    """, (user_id,))
    recent = [dict(r) for r in cursor.fetchall()]
    avg_health = (sum(r["health_score"] for r in recent) / len(recent)
                  if recent else 0)
    conn.close()
    return {"total_sessions": total_sessions, "recent_health": recent,
            "avg_health": round(avg_health, 1)}


def create_session_token(user_id: int) -> str:
    """Buat token sesi baru untuk user."""
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now() + timedelta(days=7)
    ).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    # Hapus token lama milik user ini
    cursor.execute(
        "DELETE FROM session_tokens WHERE user_id = ?",
        (user_id,)
    )

    cursor.execute("""
        INSERT INTO session_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token, expires_at))

    conn.commit()
    conn.close()
    return token


def verify_session_token(token: str) -> dict | None:
    """
    Verifikasi token sesi.
    Return user dict jika valid, None jika tidak.
    """
    if not token:
        return None

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.*, st.expires_at as token_expires_at
        FROM session_tokens st
        JOIN users u ON st.user_id = u.id
        WHERE st.token = ?
    """, (token,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    row_dict = dict(row)

    # Cek apakah token sudah expired
    expires = datetime.strptime(
        row_dict["token_expires_at"],
        "%Y-%m-%d %H:%M:%S"
    )
    if datetime.now() > expires:
        return None

    row_dict.pop("password_hash", None)
    row_dict.pop("token_expires_at", None)
    return row_dict


def delete_session_token(user_id: int):
    """Hapus semua token sesi user (logout)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM session_tokens WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_user_baselines(user_id: int, business_type: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM spending_baselines
        WHERE user_id = ? AND business_type = ?
        ORDER BY avg_monthly DESC
    """, (user_id, business_type))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Transaction
# ══════════════════════════════════════════════════════════════════

def save_transactions(transactions: list[dict], session_id: str,
                      user_id: int = None) -> int:
    """Simpan list transaksi ke database. Return jumlah row yang disimpan."""
    conn = get_connection()
    cursor = conn.cursor()
    saved = 0

    for tx in transactions:
        cursor.execute("""
            INSERT INTO transactions
                (date, amount, type, description, category, sub_category,
                 is_recurring, is_business, confidence, source, session_id,
                 user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx.get("date"), tx.get("amount"), tx.get("type"),
            tx.get("description"), tx.get("category"),
            tx.get("sub_category"),
            1 if tx.get("is_recurring") else 0,
            1 if tx.get("is_business", True) else 0,
            tx.get("confidence", 1.0), tx.get("source", "manual"),
            session_id, user_id,
        ))
        saved += 1

    conn.commit()
    conn.close()
    return saved


def get_transactions(
    session_id: str = None, start_date: str = None,
    end_date: str = None, tx_type: str = None,
    business_only: bool = True, user_id: int = None,
) -> list[dict]:
    """Ambil transaksi dengan berbagai filter."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if tx_type:
        query += " AND type = ?"
        params.append(tx_type)
    if business_only:
        query += " AND is_business = 1"
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY date DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_spending_by_category(
    start_date: str = None, end_date: str = None,
    business_type: str = "general", user_id: int = None,
) -> list[dict]:
    """Ambil total pengeluaran per kategori dalam periode tertentu."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT category, SUM(amount) as total,
               COUNT(*) as transaction_count, AVG(amount) as avg_amount
        FROM transactions
        WHERE type = 'expense' AND is_business = 1 AND category IS NOT NULL
    """
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " GROUP BY category ORDER BY total DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Analytics
# ══════════════════════════════════════════════════════════════════

def save_analytics(analytics: dict, session_id: str, user_id: int = None):
    """Simpan hasil kalkulasi Financial Analyst Agent."""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analytics (
            session_id, period_start, period_end,
            total_income, total_expense, net_cashflow, cash_balance,
            burn_rate_daily, burn_rate_monthly, gross_margin,
            runway_days, revenue_consistency,
            health_score, health_score_prev, health_score_industry,
            health_score_threshold, forecast_30d, narrative,
            business_type, user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        analytics.get("period_start"), analytics.get("period_end"),
        analytics.get("total_income", 0), analytics.get("total_expense", 0),
        analytics.get("net_cashflow", 0), analytics.get("cash_balance", 0),
        analytics.get("burn_rate_daily", 0), analytics.get("burn_rate_monthly", 0),
        analytics.get("gross_margin", 0), analytics.get("runway_days", 0),
        analytics.get("revenue_consistency", 0),
        analytics.get("health_score", 0), analytics.get("health_score_prev", 0),
        analytics.get("health_score_industry", 0),
        analytics.get("health_score_threshold", 50),
        json.dumps(analytics.get("forecast_30d", [])),
        analytics.get("narrative", ""),
        analytics.get("business_type", "general"), user_id,
    ))
    conn.commit()
    conn.close()


def get_latest_analytics(business_type: str = None,
                         user_id: int = None) -> dict | None:
    """Ambil hasil analitik terbaru."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM analytics WHERE 1=1"
    params = []
    if business_type:
        query += " AND business_type = ?"
        params.append(business_type)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY created_at DESC LIMIT 1"
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Anomalies
# ══════════════════════════════════════════════════════════════════

def save_anomalies(anomalies: list[dict], session_id: str,
                   user_id: int = None):
    """Simpan anomali yang ditemukan Anomaly Agent."""
    conn = get_connection()
    cursor = conn.cursor()
    for a in anomalies:
        cursor.execute("""
            INSERT INTO anomalies
                (session_id, category, severity, current_amount,
                 baseline_amount, deviation_pct, description, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, a.get("category"), a.get("severity"),
            a.get("current_amount"), a.get("baseline_amount"),
            a.get("deviation_pct"), a.get("description"), user_id,
        ))
    conn.commit()
    conn.close()


def get_anomalies(session_id: str = None, severity: str = None,
                  user_id: int = None) -> list[dict]:
    """Ambil anomali dengan filter opsional."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM anomalies WHERE 1=1"
    params = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY severity DESC, deviation_pct DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Recommendations
# ══════════════════════════════════════════════════════════════════

def save_recommendations(recommendations: list[dict], session_id: str,
                         user_id: int = None):
    """Simpan rekomendasi dari Advisor Agent."""
    conn = get_connection()
    cursor = conn.cursor()
    for r in recommendations:
        cursor.execute("""
            INSERT INTO recommendations
                (session_id, priority, title, description, impact,
                 urgency, category, early_warning,
                 confidence_min, confidence_max, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, r.get("priority"), r.get("title"),
            r.get("description"), r.get("impact"), r.get("urgency"),
            r.get("category"), r.get("early_warning"),
            r.get("confidence_min"), r.get("confidence_max"), user_id,
        ))
    conn.commit()
    conn.close()


def get_recommendations(session_id: str = None,
                        user_id: int = None) -> list[dict]:
    """Ambil rekomendasi terbaru."""
    conn = get_connection()
    cursor = conn.cursor()
    if session_id:
        query = "SELECT * FROM recommendations WHERE session_id = ?"
        params = [session_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY priority"
        cursor.execute(query, params)
    else:
        base = """
            SELECT r.* FROM recommendations r
            JOIN (SELECT session_id, MAX(created_at) as max_date
                  FROM recommendations"""
        if user_id:
            base += " WHERE user_id = ?"
        base += """ GROUP BY session_id
                  ORDER BY max_date DESC LIMIT 1) latest
            ON r.session_id = latest.session_id
            ORDER BY r.priority"""
        cursor.execute(base, (user_id,) if user_id else ())
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Agent Logs
# ══════════════════════════════════════════════════════════════════

def log_agent_step(
    session_id: str, agent_name: str, step: int,
    input_summary: str, reasoning: str, output_summary: str,
    duration_ms: int = 0, status: str = "success",
    user_id: int = None,
):
    """Simpan satu langkah reasoning agent ke log."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_logs
            (session_id, agent_name, step, input_summary,
             reasoning, output_summary, duration_ms, status, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, agent_name, step, input_summary,
          reasoning, output_summary, duration_ms, status, user_id))
    conn.commit()
    conn.close()


def get_agent_logs(session_id: str, user_id: int = None) -> list[dict]:
    """Ambil semua log agent untuk satu session."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM agent_logs WHERE session_id = ?"
    params = [session_id]
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY agent_name, step"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Baselines & Memory
# ══════════════════════════════════════════════════════════════════

def get_spending_baselines(business_type: str,
                           user_id: int = None) -> list[dict]:
    """Ambil baseline pengeluaran per kategori untuk deteksi anomali."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM spending_baselines WHERE business_type = ?"
    params = [business_type]
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY avg_monthly DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_baseline(category: str, business_type: str,
                  avg_monthly: float, std_deviation: float,
                  sample_months: int, user_id: int = None):
    """Simpan atau update baseline per kategori."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO spending_baselines
            (category, business_type, avg_monthly, std_deviation,
             sample_months, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(category, business_type) DO UPDATE SET
            avg_monthly = excluded.avg_monthly,
            std_deviation = excluded.std_deviation,
            sample_months = excluded.sample_months,
            updated_at = datetime('now', 'localtime')
    """, (category, business_type, avg_monthly, std_deviation,
          sample_months, user_id))
    conn.commit()
    conn.close()


def get_monthly_snapshots(business_type: str = None,
                          last_n_months: int = 6,
                          user_id: int = None) -> list[dict]:
    """Ambil snapshot bulanan untuk analisis tren historis."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM monthly_snapshots WHERE 1=1"
    params = []
    if business_type:
        query += " AND business_type = ?"
        params.append(business_type)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY year_month DESC LIMIT ?"
    params.append(last_n_months)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_monthly_snapshot(snapshot: dict, user_id: int = None):
    """Simpan atau update snapshot bulanan."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO monthly_snapshots
            (year_month, total_income, total_expense, net_cashflow,
             health_score, burn_rate, runway_days, business_type, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(year_month) DO UPDATE SET
            total_income = excluded.total_income,
            total_expense = excluded.total_expense,
            net_cashflow = excluded.net_cashflow,
            health_score = excluded.health_score,
            burn_rate = excluded.burn_rate,
            runway_days = excluded.runway_days
    """, (
        snapshot.get("year_month"),
        snapshot.get("total_income", 0), snapshot.get("total_expense", 0),
        snapshot.get("net_cashflow", 0), snapshot.get("health_score", 0),
        snapshot.get("burn_rate", 0), snapshot.get("runway_days", 0),
        snapshot.get("business_type", "general"), user_id,
    ))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT — Test database
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_database()

    # Quick test
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    conn.close()

    print("\n📊 Tables created:")
    for t in tables:
        print(f"   ✓ {t['name']}")
