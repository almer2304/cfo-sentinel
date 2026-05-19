"""Test queries untuk user_id=4 (Warung Ombe / roni@gmail.com)"""
from core.database_new import get_financial_summary, get_cash_balance, get_transactions_by_user
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
today = datetime.now(WIB).strftime('%Y-%m-%d')
month_start = datetime.now(WIB).strftime('%Y-%m-01')

USER_ID = 4  # Warung Ombe
print(f"=== TEST USER_ID={USER_ID} (Warung Ombe) ===")
print(f"Periode bulan ini: {month_start} s/d {today}\n")

summary_today = get_financial_summary(USER_ID, today, today)
print("--- HARI INI ---")
print(f"  income : Rp {summary_today.get('total_income', 0) or 0:,.0f}")
print(f"  expense: Rp {summary_today.get('total_expense', 0) or 0:,.0f}")
print(f"  net    : Rp {summary_today.get('net_cashflow', 0) or 0:,.0f}")

summary_month = get_financial_summary(USER_ID, month_start, today)
print("\n--- BULAN INI ---")
print(f"  income : Rp {summary_month.get('total_income', 0) or 0:,.0f}")
print(f"  expense: Rp {summary_month.get('total_expense', 0) or 0:,.0f}")
print(f"  net    : Rp {summary_month.get('net_cashflow', 0) or 0:,.0f}")
print(f"  tx cnt : {summary_month.get('total_tx', 0) or 0}")

cash = get_cash_balance(USER_ID)
print(f"\n--- SALDO KAS (semua waktu) ---")
print(f"  cash_balance: Rp {cash:,.0f}")

print("\n--- 15 TRANSAKSI TERAKHIR ---")
txs = get_transactions_by_user(USER_ID, limit=15)
for t in txs:
    sign = "+" if t.get("type") == "income" else "-"
    tipe = "Pemasukan" if t.get("type") == "income" else "Pengeluaran"
    amt  = t.get("amount", 0) or 0
    print(f"  [{t.get('date_only','')}] {tipe} {sign}Rp {amt:,.0f} -- {t.get('description','')} ({t.get('category','')})")
