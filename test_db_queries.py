"""Test script untuk verifikasi database queries"""
from core.database_new import get_financial_summary, get_cash_balance, get_transactions_by_user
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
today = datetime.now(WIB).strftime('%Y-%m-%d')
month_start = datetime.now(WIB).strftime('%Y-%m-01')

user_id = 1
print("=== TEST AGGREGATE QUERY (all time) ===")
summary = get_financial_summary(user_id, '2024-01-01', today)
income  = summary.get("total_income", 0) or 0
expense = summary.get("total_expense", 0) or 0
net     = summary.get("net_cashflow", 0) or 0
tx_cnt  = summary.get("total_tx", 0) or 0
print(f"  total_income:  Rp {income:,.0f}")
print(f"  total_expense: Rp {expense:,.0f}")
print(f"  net_cashflow:  Rp {net:,.0f}")
print(f"  total_tx:      {tx_cnt}")

cash = get_cash_balance(user_id)
print(f"  cash_balance:  Rp {cash:,.0f}")

print("\n=== BULAN INI ===")
summary_m = get_financial_summary(user_id, month_start, today)
print(f"  income:  Rp {summary_m.get('total_income', 0) or 0:,.0f}")
print(f"  expense: Rp {summary_m.get('total_expense', 0) or 0:,.0f}")

print("\n=== 5 TRANSAKSI TERAKHIR ===")
txs = get_transactions_by_user(user_id, limit=5)
print(f"  Total rows returned: {len(txs)}")
for t in txs:
    amt = t.get("amount", 0) or 0
    print(f"  [{t.get('type','?')}] Rp {amt:,.0f} -- {t.get('description','')} ({t.get('date_only','')})")
