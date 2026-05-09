"""
core/seed_data.py
CFO Sentinel — Synthetic Data Generator

Generate data historis simulasi 3 bulan untuk:
1. Cold start problem — user baru langsung punya baseline
2. Demo — sistem terlihat sudah berjalan berbulan-bulan
3. Testing — data konsisten untuk unit tests
"""

import random
import uuid
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

from database import init_database, save_transactions, save_monthly_snapshot
from memory import generate_cold_start_baselines


# Template transaksi per jenis bisnis
TRANSACTION_TEMPLATES = {
    "kuliner": {
        "income": [
            ("Penjualan makanan", 800_000, 3_500_000),
            ("Penjualan minuman", 300_000, 1_200_000),
            ("Katering", 1_500_000, 5_000_000),
            ("Pesanan online", 500_000, 2_000_000),
        ],
        "expense": [
            ("Beli bahan baku sayur", "Bahan Baku", 200_000, 800_000, False),
            ("Beli daging", "Bahan Baku", 500_000, 2_000_000, True),
            ("Beli bumbu dapur", "Bahan Baku", 100_000, 400_000, True),
            ("Beli kemasan", "Bahan Baku", 150_000, 500_000, True),
            ("Bayar sewa tempat", "Operasional", 2_000_000, 5_000_000, True),
            ("Bayar listrik", "Operasional", 300_000, 800_000, True),
            ("Bayar gas", "Operasional", 200_000, 600_000, True),
            ("Gaji karyawan", "SDM", 2_000_000, 4_000_000, True),
            ("Iklan Instagram", "Marketing", 100_000, 500_000, False),
            ("Bensin antar pesanan", "Operasional", 50_000, 200_000, False),
        ],
    },
    "fashion": {
        "income": [
            ("Penjualan baju", 500_000, 5_000_000),
            ("Penjualan aksesoris", 100_000, 800_000),
            ("Penjualan online Shopee", 300_000, 3_000_000),
            ("Penjualan Tokopedia", 300_000, 2_500_000),
        ],
        "expense": [
            ("Beli kain", "Bahan Baku", 500_000, 3_000_000, False),
            ("Beli benang aksesoris", "Bahan Baku", 100_000, 400_000, True),
            ("Beli kemasan", "Bahan Baku", 100_000, 300_000, True),
            ("Bayar penjahit", "SDM", 1_000_000, 3_000_000, True),
            ("Bayar sewa toko", "Operasional", 1_500_000, 4_000_000, True),
            ("Bayar listrik", "Operasional", 200_000, 500_000, True),
            ("Iklan Facebook Ads", "Marketing", 200_000, 1_000_000, False),
            ("Ongkir kirim produk", "Operasional", 100_000, 500_000, False),
        ],
    },
    "jasa": {
        "income": [
            ("Bayaran proyek", 2_000_000, 15_000_000),
            ("Retainer klien", 3_000_000, 8_000_000),
            ("Konsultasi", 500_000, 3_000_000),
            ("Pelatihan", 1_000_000, 5_000_000),
        ],
        "expense": [
            ("Gaji karyawan", "SDM", 3_000_000, 8_000_000, True),
            ("Bayar freelancer", "SDM", 500_000, 3_000_000, False),
            ("Sewa kantor", "Operasional", 2_000_000, 6_000_000, True),
            ("Bayar internet", "Operasional", 300_000, 700_000, True),
            ("Bayar software tools", "Operasional", 200_000, 800_000, True),
            ("Iklan Google Ads", "Marketing", 300_000, 2_000_000, False),
            ("Transport klien", "Operasional", 100_000, 500_000, False),
        ],
    },
    "retail": {
        "income": [
            ("Penjualan produk", 500_000, 8_000_000),
            ("Penjualan grosir", 2_000_000, 10_000_000),
            ("Penjualan online", 300_000, 3_000_000),
        ],
        "expense": [
            ("Beli stok barang", "Bahan Baku", 2_000_000, 10_000_000, True),
            ("Bayar sewa toko", "Operasional", 1_500_000, 5_000_000, True),
            ("Bayar listrik", "Operasional", 300_000, 700_000, True),
            ("Gaji karyawan", "SDM", 1_500_000, 4_000_000, True),
            ("Iklan promosi", "Marketing", 200_000, 1_000_000, False),
            ("Ongkir barang masuk", "Operasional", 100_000, 500_000, False),
        ],
    },
}


def generate_seed_data(
    business_type: str = "kuliner",
    months_back: int = 3,
    monthly_revenue_avg: float = 15_000_000,
    monthly_expense_avg: float = 12_000_000,
    seed: int = 42,
) -> dict:
    """
    Generate data transaksi simulasi untuk N bulan ke belakang.

    Args:
        business_type: jenis bisnis (kuliner/fashion/jasa/retail)
        months_back: berapa bulan ke belakang yang di-generate
        monthly_revenue_avg: rata-rata pemasukan per bulan
        monthly_expense_avg: rata-rata pengeluaran per bulan
        seed: random seed untuk reproducibility

    Returns:
        dict dengan summary hasil generation
    """
    random.seed(seed)

    templates = TRANSACTION_TEMPLATES.get(
        business_type,
        TRANSACTION_TEMPLATES["kuliner"]
    )

    all_transactions = []
    monthly_summaries = []

    today = date.today()

    for month_offset in range(months_back, 0, -1):
        month_start = (today - relativedelta(months=month_offset)).replace(day=1)
        month_end   = (month_start + relativedelta(months=1)) - timedelta(days=1)
        year_month  = month_start.strftime("%Y-%m")

        session_id = f"seed_{year_month}"
        month_transactions = []
        month_income  = 0
        month_expense = 0

        # Generate income transactions (8-15 per bulan)
        n_income = random.randint(8, 15)
        income_templates = templates["income"]

        for _ in range(n_income):
            template = random.choice(income_templates)
            amount = random.uniform(template[1], template[2])

            # Sedikit variasi antar bulan
            if month_offset == 1:  # bulan terakhir — tren turun sedikit
                amount *= random.uniform(0.85, 1.0)

            tx_date = month_start + timedelta(
                days=random.randint(0, (month_end - month_start).days)
            )

            tx = {
                "date":        tx_date.strftime("%Y-%m-%d"),
                "amount":      round(amount, -3),  # Bulatkan ke ribuan
                "type":        "income",
                "description": template[0],
                "category":    "Penjualan",
                "sub_category": "Produk",
                "is_recurring": False,
                "is_business": True,
                "confidence":  1.0,
                "source":      "seed",
            }
            month_transactions.append(tx)
            month_income += tx["amount"]

        # Generate expense transactions (10-20 per bulan)
        n_expense = random.randint(10, 20)
        expense_templates = templates["expense"]

        for _ in range(n_expense):
            template = random.choice(expense_templates)
            desc, category, min_amt, max_amt, is_recurring = template
            amount = random.uniform(min_amt, max_amt)

            # Bulan terakhir — pengeluaran naik sedikit (untuk demo anomali)
            if month_offset == 1 and category == "Operasional":
                amount *= random.uniform(1.1, 1.5)

            tx_date = month_start + timedelta(
                days=random.randint(0, (month_end - month_start).days)
            )

            tx = {
                "date":        tx_date.strftime("%Y-%m-%d"),
                "amount":      round(amount, -3),
                "type":        "expense",
                "description": desc,
                "category":    category,
                "sub_category": "Lainnya",
                "is_recurring": is_recurring,
                "is_business": True,
                "confidence":  1.0,
                "source":      "seed",
            }
            month_transactions.append(tx)
            month_expense += tx["amount"]

        # Simpan ke database
        save_transactions(month_transactions, session_id)

        net        = month_income - month_expense
        burn_rate  = month_expense / 30
        cash_bal   = max(0, net * random.uniform(2, 4))
        runway     = cash_bal / burn_rate if burn_rate > 0 else 999

        # Hitung health score sederhana
        margin = (net / month_income * 100) if month_income > 0 else 0
        health = min(100, max(0,
            (margin / 30) * 40 +      # margin kontribusi 40%
            (min(runway, 60) / 60) * 40 +  # runway kontribusi 40%
            20                         # base score
        ))

        # Simpan snapshot bulanan
        save_monthly_snapshot({
            "year_month":    year_month,
            "total_income":  month_income,
            "total_expense": month_expense,
            "net_cashflow":  net,
            "health_score":  round(health, 1),
            "burn_rate":     burn_rate,
            "runway_days":   runway,
            "business_type": business_type,
        })

        monthly_summaries.append({
            "year_month":  year_month,
            "income":      month_income,
            "expense":     month_expense,
            "net":         net,
            "health":      round(health, 1),
            "n_tx":        len(month_transactions),
        })

        all_transactions.extend(month_transactions)

    # Generate cold start baselines
    generate_cold_start_baselines(
        business_type,
        total_monthly_expense=monthly_expense_avg
    )

    return {
        "business_type":    business_type,
        "months_generated": months_back,
        "total_transactions": len(all_transactions),
        "monthly_summaries": monthly_summaries,
    }


def run_demo_seed():
    """
    Jalankan seed data untuk skenario demo kompetisi:
    UMKM kuliner yang penjualan mulai turun & pengeluaran naik.
    Ini skenario yang paling powerful untuk demo ke juri.
    """
    print("🌱 Generating demo seed data...")
    print("   Skenario: UMKM kuliner — penjualan turun, pengeluaran naik\n")

    result = generate_seed_data(
        business_type="kuliner",
        months_back=3,
        monthly_revenue_avg=15_000_000,
        monthly_expense_avg=12_000_000,
        seed=42,
    )

    print(f"✅ Seed data generated!")
    print(f"   Business type: {result['business_type']}")
    print(f"   Months: {result['months_generated']}")
    print(f"   Total transactions: {result['total_transactions']}")
    print(f"\n   Monthly breakdown:")

    for m in result["monthly_summaries"]:
        status = "⚠️ " if m["health"] < 65 else "✅"
        print(
            f"   {status} {m['year_month']}: "
            f"Income Rp {m['income']:>12,.0f} | "
            f"Expense Rp {m['expense']:>12,.0f} | "
            f"Health {m['health']:>5.1f}/100 | "
            f"{m['n_tx']} transaksi"
        )

    return result


if __name__ == "__main__":
    from database import init_database
    init_database()
    run_demo_seed()