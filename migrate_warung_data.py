"""
Migrasi data: Insert transaksi yang disebutkan user ke database.
Semua transaksi ini adalah input HARI INI dari Warung Ombe (user_id=4 / roni@gmail.com).

PRINSIP AYAH (AKUNTAN):
- Pemasukan = Penjualan (income) — SAMA
- Pengeluaran = Pembelian (expense) — SAMA
- Saldo = Total Pemasukan - Total Pengeluaran = Laba Kotor Sementara
"""
from core.database_new import save_transaction_simple, get_financial_summary, get_cash_balance
from core.database import get_connection
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
USER_ID = 4  # Warung Ombe / roni@gmail.com
today = datetime.now(WIB).strftime("%Y-%m-%d")

print(f"=== MEMASUKKAN TRANSAKSI HARI INI ({today}) untuk user_id={USER_ID} ===\n")

# ─── PENGELUARAN / PEMBELIAN ─────────────────────────────────────────────────
pengeluaran = [
    {"description": "Beli pompa air",    "amount": 200000, "category": "Pembelian Barang Dagangan"},
    {"description": "Beli kipas angin",  "amount": 100000, "category": "Pembelian Barang Dagangan"},
    {"description": "Beli kursi warung", "amount": 50000,  "category": "Pembelian Aset/Perlengkapan"},
    {"description": "Beli sukun",        "amount": 10000,  "category": "Pembelian Bahan Baku"},
]

print("--- PENGELUARAN / PEMBELIAN ---")
total_expense = 0
for item in pengeluaran:
    tx = save_transaction_simple(
        user_id=USER_ID,
        type="expense",
        amount=item["amount"],
        description=item["description"],
        category=item["category"],
    )
    total_expense += item["amount"]
    print(f"  [OK] [{tx['transaction_code']}] {item['description']}: Rp {item['amount']:,.0f}")

print(f"  TOTAL PENGELUARAN: Rp {total_expense:,.0f}\n")

# ─── PEMASUKAN / PENJUALAN ───────────────────────────────────────────────────
pemasukan = [
    {"description": "Penjualan kipas angin",    "amount": 250000,  "category": "Penjualan Barang"},
    {"description": "Penjualan pompa air Almer", "amount": 500000, "category": "Penjualan Barang"},
    {"description": "Jual nasi uduk (pagi)",     "amount": 15000,  "category": "Penjualan Makanan"},
    {"description": "Jual gorengan (pagi)",      "amount": 30000,  "category": "Penjualan Makanan"},
    {"description": "Jual nasi uduk (sore)",     "amount": 15000,  "category": "Penjualan Makanan"},
    {"description": "Jual gorengan (sore)",      "amount": 40000,  "category": "Penjualan Makanan"},
    {"description": "Penjualan minuman",         "amount": 100000, "category": "Penjualan Minuman"},
    {"description": "Jual minuman (4 transaksi)","amount": 100000, "category": "Penjualan Minuman"},
]

print("--- PEMASUKAN / PENJUALAN ---")
total_income = 0
for item in pemasukan:
    tx = save_transaction_simple(
        user_id=USER_ID,
        type="income",
        amount=item["amount"],
        description=item["description"],
        category=item["category"],
    )
    total_income += item["amount"]
    print(f"  [OK] [{tx['transaction_code']}] {item['description']}: Rp {item['amount']:,.0f}")

print(f"  TOTAL PEMASUKAN: Rp {total_income:,.0f}\n")

# ─── RINGKASAN ───────────────────────────────────────────────────────────────
selisih = total_income - total_expense
print("=" * 50)
print("RINGKASAN TRANSAKSI HARI INI")
print("=" * 50)
print(f"  Total Pemasukan / Penjualan : Rp {total_income:,.0f}")
print(f"  Total Pengeluaran / Pembelian: Rp {total_expense:,.0f}")
print(f"  Selisih / Laba Kotor Sementara: Rp {selisih:,.0f}")
print()

# Verifikasi dari DB
print("=== VERIFIKASI DARI DATABASE ===")
summary = get_financial_summary(USER_ID, today, today)
cash = get_cash_balance(USER_ID)
print(f"  DB income hari ini : Rp {summary.get('total_income', 0) or 0:,.0f}")
print(f"  DB expense hari ini: Rp {summary.get('total_expense', 0) or 0:,.0f}")
print(f"  DB net hari ini    : Rp {summary.get('net_cashflow', 0) or 0:,.0f}")
print(f"  Saldo Kas Total    : Rp {cash:,.0f}")
print()
print("✅ SESUAI dengan prinsip akuntansi:")
print("   Pemasukan (income) = Penjualan (revenue) — istilah sama")
print("   Pengeluaran (expense) = Pembelian (purchase cost) — istilah sama")
print("   Saldo Kas = Akumulasi (Pemasukan - Pengeluaran) dari semua transaksi")
