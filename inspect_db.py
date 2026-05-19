"""Audit lengkap data Warung Ombe (user_id=4)"""
from core.database import get_connection
conn = get_connection()
cursor = conn.cursor()

print("=== TRANSAKSI USER_ID=4 (Warung Ombe) ===")
cursor.execute("""
    SELECT id, transaction_code, date, date_only, type, amount, description, category, source
    FROM transactions
    WHERE user_id=4
    ORDER BY COALESCE(NULLIF(date_only,''), date) DESC
""")
for r in cursor.fetchall():
    print(f"  [{r['id']}] code={r['transaction_code']} date={r['date'] or r['date_only']} {r['type']} Rp {r['amount']:,.0f} -- {r['description']} (cat={r['category']}, src={r['source']})")

print("\n=== ANALYTICS USER_ID=4 ===")
cursor.execute("""
    SELECT total_income, total_expense, cash_balance, health_score, created_at
    FROM analytics WHERE user_id=4 ORDER BY created_at DESC
""")
for r in cursor.fetchall():
    print(f"  income={r['total_income']:,.0f} expense={r['total_expense']:,.0f} saldo={r['cash_balance']:,.0f} score={r['health_score']} at={r['created_at']}")

# Hitung yang seharusnya dari transaksi yang user sebutkan
print("\n=== SEHARUSNYA (dari input user) ===")
print("  Pembelian/Pengeluaran:")
items_expense = [
    ("Beli pompa air", 200000),
    ("Beli kipas angin", 100000),
    ("Beli kursi warung", 50000),
    ("Beli sukun", 10000),
]
total_e = sum(v for _, v in items_expense)
for name, val in items_expense:
    print(f"    {name}: Rp {val:,.0f}")
print(f"  TOTAL PENGELUARAN: Rp {total_e:,.0f}")

print("  Penjualan/Pemasukan:")
items_income = [
    ("Penjualan kipas angin", 250000),
    ("Penjualan pompa air Almer", 500000),
    ("Jual nasi uduk", 15000),
    ("Jual gorengan", 30000),
    ("Jual nasi uduk", 15000),
    ("Jual gorengan", 40000),
    ("Penjualan minuman", 100000),
    ("Jual minuman x4", 100000),
]
total_i = sum(v for _, v in items_income)
for name, val in items_income:
    print(f"    {name}: Rp {val:,.0f}")
print(f"  TOTAL PEMASUKAN: Rp {total_i:,.0f}")
print(f"  SELISIH/LABA KOTOR: Rp {total_i - total_e:,.0f}")

conn.close()
