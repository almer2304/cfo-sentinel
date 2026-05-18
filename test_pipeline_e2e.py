"""
test_pipeline_e2e.py
Test end-to-end pipeline: simpan transaksi → jalankan Agent 1-5 → cek hasil DB.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

from core.database import init_database
from core.database_new import (
    init_new_tables, save_transaction_simple,
    get_daily_summary, get_cash_balance
)
from core.pipeline import _run_pipeline
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

print("[1] Init database...")
init_database()
init_new_tables()
print("    [OK] DB siap")

print()
print("[2] Simpan transaksi test...")
tx = save_transaction_simple(
    user_id=1,
    type="expense",
    amount=500000,
    description="Beli bahan baku ayam ke pasar",
    category="Bahan Baku",
    notes="untuk stok seminggu",
)
print(f"    [OK] Tersimpan: {tx['transaction_code']}")
print(f"    datetime_wib : {tx['datetime_wib']}")

print()
print("[3] Jalankan pipeline (synchronous untuk test)...")
_run_pipeline(tx, user_id=1)

print()
print("[4] Cek hasil di daily_summaries...")
today = datetime.now(WIB).strftime("%Y-%m-%d")
summary = get_daily_summary(1, today)
if summary:
    print(f"    Health Score  : {summary.get('health_score', 0)}")
    narrative = summary.get("agent_narrative", "")
    print(f"    Narrative     : {str(narrative)[:120]}...")
    print(f"    Anomaly Count : {summary.get('anomaly_count', 0)}")
    print(f"    Processed at  : {summary.get('processed_at', '')}")
else:
    print("    [WARN] Tidak ada data di daily_summaries")

balance = get_cash_balance(1)
print(f"    Cash Balance  : Rp {balance:,.0f}")

print()
print("[5] Cek transaksi sudah terklasifikasi...")
from core.database import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute("""
    SELECT transaction_code, accounting_type, category, agent_classified
    FROM transactions
    WHERE transaction_code = ?
""", (tx["transaction_code"],))
row = cursor.fetchone()
conn.close()
if row:
    print(f"    Code         : {row['transaction_code']}")
    print(f"    Acct Type    : {row['accounting_type']}")
    print(f"    Category     : {row['category']}")
    print(f"    Classified   : {'Yes' if row['agent_classified'] else 'No'}")
else:
    print("    [WARN] Transaksi tidak ditemukan di DB")

print()
print("=" * 50)
print("PIPELINE END-TO-END TEST SELESAI!")
print("=" * 50)
