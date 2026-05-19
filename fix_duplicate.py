"""
Hapus transaksi duplikat yang terjadi karena script dijalankan dua kali.
Hanya hapus 1 beli pompa air yang duplikat (TRX terlama).
"""
from core.database import get_connection

conn = get_connection()
cursor = conn.cursor()

# Lihat semua transaksi beli pompa air hari ini
cursor.execute("""
    SELECT id, transaction_code, datetime_wib, amount, description
    FROM transactions
    WHERE user_id=4 AND description='Beli pompa air'
    ORDER BY id ASC
""")
rows = cursor.fetchall()
print("Transaksi 'Beli pompa air':")
for r in rows:
    print(f"  id={r['id']} code={r['transaction_code']} datetime={r['datetime_wib']}")

if len(rows) > 1:
    # Hapus yang pertama (duplikat dari run pertama yang gagal)
    first_id = rows[0]['id']
    cursor.execute("UPDATE transactions SET is_deleted=1 WHERE id=?", (first_id,))
    conn.commit()
    print(f"\nDeleted duplicate id={first_id}")

# Verifikasi
cursor.execute("""
    SELECT COUNT(*), type, SUM(amount) as total
    FROM transactions
    WHERE user_id=4 AND date_only='2026-05-19' AND (is_deleted IS NULL OR is_deleted=0)
    GROUP BY type
""")
print("\nVerifikasi hari ini (2026-05-19):")
for r in cursor.fetchall():
    print(f"  {r['type']}: {r[0]} transaksi, total Rp {r['total']:,.0f}")

conn.close()
