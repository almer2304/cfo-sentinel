"""
dashboard/demo_mode.py
CFO Sentinel — Demo Mode

Pre-cached output untuk demo kepada juri.
Menghindari variasi non-deterministic dari LLM saat presentasi.
Hemat token + respons instan saat demo.

Cara aktifkan: set DEMO_MODE=true di .env
"""

from core.schemas import (
    PipelineState,
    ParserOutput,
    ParsedTransaction,
    CategorizerOutput,
    CategorizedTransaction,
    AnalystOutput,
    HealthScore,
    ConfidenceRange,
    ForecastPoint,
    AnomalyOutput,
    Anomaly,
    ScenarioOutput,
    CostItem,
    AdvisorOutput,
    ActionItem,
    EarlyWarning,
)

# ── Demo session ID (fixed agar reproducible) ──────────────────────
DEMO_SESSION_ID = "demo-2026-warung-sate-padang"


def get_demo_state() -> PipelineState:
    """
    Return pre-cached PipelineState untuk demo.
    Skenario: Warung Sate Padang "Pak Rizal" — bisnis kuliner kecil.
    """
    state = PipelineState(
        session_id=DEMO_SESSION_ID,
        raw_input=_DEMO_RAW_INPUT,
        business_type="kuliner",
        current_cash_balance=4_500_000,
        is_demo_mode=True,
    )

    state.parser_output      = _build_parser_output()
    state.categorizer_output = _build_categorizer_output()
    state.analyst_output     = _build_analyst_output()
    state.anomaly_output     = _build_anomaly_output()
    state.scenario_output    = _build_scenario_output()
    state.advisor_output     = _build_advisor_output()
    state.current_step       = "done"

    return state


# ══════════════════════════════════════════════════════════════════
# RAW INPUT
# ══════════════════════════════════════════════════════════════════

_DEMO_RAW_INPUT = """
Minggu ini:
- Senin beli daging sapi 2kg 180rb, beli bumbu 45rb
- Selasa bayar sewa lapak 500rb bulanan
- Rabu dapet orderan katering 3.5jt (lunas)
- Kamis beli arang dan kayu 60rb, beli lontong 80rb
- Jumat gajian karyawan 1 orang 1.2jt
- Sabtu penjualan langsung 1.8jt, minus bahan baku 340rb
- Minggu penjualan 2.1jt, ada yg bayar piutang 500rb
"""


# ══════════════════════════════════════════════════════════════════
# PRE-BUILT OUTPUTS
# ══════════════════════════════════════════════════════════════════

def _build_parser_output() -> ParserOutput:
    transactions = [
        ParsedTransaction(date="2026-05-04", amount=180_000,  type="expense", description="Beli daging sapi 2kg",       is_business=True, confidence=0.98),
        ParsedTransaction(date="2026-05-04", amount=45_000,   type="expense", description="Beli bumbu masak",            is_business=True, confidence=0.97),
        ParsedTransaction(date="2026-05-05", amount=500_000,  type="expense", description="Sewa lapak bulanan",          is_business=True, confidence=0.99),
        ParsedTransaction(date="2026-05-06", amount=3_500_000,type="income",  description="Order katering (lunas)",      is_business=True, confidence=0.99),
        ParsedTransaction(date="2026-05-07", amount=60_000,   type="expense", description="Beli arang dan kayu bakar",   is_business=True, confidence=0.96),
        ParsedTransaction(date="2026-05-07", amount=80_000,   type="expense", description="Beli lontong",                is_business=True, confidence=0.97),
        ParsedTransaction(date="2026-05-08", amount=1_200_000,type="expense", description="Gaji karyawan",               is_business=True, confidence=0.99),
        ParsedTransaction(date="2026-05-09", amount=1_800_000,type="income",  description="Penjualan langsung Sabtu",    is_business=True, confidence=0.98),
        ParsedTransaction(date="2026-05-09", amount=340_000,  type="expense", description="Bahan baku Sabtu",            is_business=True, confidence=0.96),
        ParsedTransaction(date="2026-05-10", amount=2_100_000,type="income",  description="Penjualan langsung Minggu",   is_business=True, confidence=0.98),
        ParsedTransaction(date="2026-05-10", amount=500_000,  type="income",  description="Pembayaran piutang pelanggan",is_business=True, confidence=0.95),
    ]
    return ParserOutput(
        session_id=DEMO_SESSION_ID,
        raw_input=_DEMO_RAW_INPUT,
        transactions=transactions,
        total_parsed=len(transactions),
        has_ambiguity=False,
        ambiguity_notes=[],
    )


def _build_categorizer_output() -> CategorizerOutput:
    transactions = [
        CategorizedTransaction(date="2026-05-04", amount=180_000,  type="expense", description="Beli daging sapi 2kg",       is_business=True, confidence=0.98, category="Bahan Baku",  sub_category="Makanan",  is_recurring=False, categorization_confidence=0.98),
        CategorizedTransaction(date="2026-05-04", amount=45_000,   type="expense", description="Beli bumbu masak",            is_business=True, confidence=0.97, category="Bahan Baku",  sub_category="Makanan",  is_recurring=False, categorization_confidence=0.97),
        CategorizedTransaction(date="2026-05-05", amount=500_000,  type="expense", description="Sewa lapak bulanan",          is_business=True, confidence=0.99, category="Operasional", sub_category="Sewa",     is_recurring=True,  categorization_confidence=0.99),
        CategorizedTransaction(date="2026-05-06", amount=3_500_000,type="income",  description="Order katering (lunas)",      is_business=True, confidence=0.99, category="Penjualan",  sub_category="Jasa",     is_recurring=False, categorization_confidence=0.99),
        CategorizedTransaction(date="2026-05-07", amount=60_000,   type="expense", description="Beli arang dan kayu bakar",   is_business=True, confidence=0.96, category="Bahan Baku",  sub_category="Lainnya",  is_recurring=False, categorization_confidence=0.95),
        CategorizedTransaction(date="2026-05-07", amount=80_000,   type="expense", description="Beli lontong",                is_business=True, confidence=0.97, category="Bahan Baku",  sub_category="Makanan",  is_recurring=False, categorization_confidence=0.97),
        CategorizedTransaction(date="2026-05-08", amount=1_200_000,type="expense", description="Gaji karyawan",               is_business=True, confidence=0.99, category="SDM",         sub_category="Gaji",     is_recurring=True,  categorization_confidence=0.99),
        CategorizedTransaction(date="2026-05-09", amount=1_800_000,type="income",  description="Penjualan langsung Sabtu",    is_business=True, confidence=0.98, category="Penjualan",  sub_category="Produk",   is_recurring=False, categorization_confidence=0.98),
        CategorizedTransaction(date="2026-05-09", amount=340_000,  type="expense", description="Bahan baku Sabtu",            is_business=True, confidence=0.96, category="Bahan Baku",  sub_category="Makanan",  is_recurring=False, categorization_confidence=0.96),
        CategorizedTransaction(date="2026-05-10", amount=2_100_000,type="income",  description="Penjualan langsung Minggu",   is_business=True, confidence=0.98, category="Penjualan",  sub_category="Produk",   is_recurring=False, categorization_confidence=0.98),
        CategorizedTransaction(date="2026-05-10", amount=500_000,  type="income",  description="Pembayaran piutang pelanggan",is_business=True, confidence=0.95, category="Piutang",    sub_category="Pelanggan",is_recurring=False, categorization_confidence=0.95),
    ]
    return CategorizerOutput(
        session_id=DEMO_SESSION_ID,
        transactions=transactions,
        total_income=7_900_000,
        total_expense=2_405_000,
        categories_found=["Bahan Baku", "Operasional", "SDM", "Penjualan", "Piutang"],
        recurring_count=2,
    )


def _build_analyst_output() -> AnalystOutput:
    forecast = []
    balance = 10_095_000.0  # cash_balance after this week
    from datetime import datetime, timedelta
    today = datetime(2026, 5, 10)
    burn_daily = 343_571.0
    for i in range(1, 31):
        d = today + timedelta(days=i)
        balance -= burn_daily
        forecast.append(ForecastPoint(
            day=i,
            date=d.strftime("%Y-%m-%d"),
            predicted_balance=balance,
            confidence_min=balance * 0.85,
            confidence_max=balance * 1.15,
        ))

    hs = HealthScore(
        current=74,
        previous_month=68,
        industry_average=72,
        danger_threshold=50,
        trend="UP",
    )

    return AnalystOutput(
        session_id=DEMO_SESSION_ID,
        period_start="2026-05-01",
        period_end="2026-05-10",
        total_income=7_900_000,
        total_expense=2_405_000,
        net_cashflow=5_495_000,
        cash_balance=10_095_000,
        burn_rate_daily=343_571,
        burn_rate_monthly=10_307_130,
        net_margin=57.5,
        runway_days=ConfidenceRange(
            minimum=23, expected=29, maximum=37,
            assumption="Pengeluaran konstan tanpa pemasukan baru",
        ),
        revenue_consistency=0.82,
        health_score=hs,
        forecast_30d=forecast,
        narrative=(
            "Warung Sate Padang Pak Rizal menunjukkan performa positif minggu ini "
            "dengan net cash flow Rp 5,5 juta dari total pemasukan Rp 7,9 juta. "
            "Health Score naik ke 74/100, melampaui rata-rata industri kuliner 72/100 — "
            "ini sinyal yang bagus. Namun dengan saldo Rp 10,1 juta dan burn rate "
            "Rp 343.571/hari, runway hanya sekitar 29 hari jika tidak ada pemasukan baru. "
            "Satu hal yang perlu diperhatikan: 44% pemasukan berasal dari order katering "
            "satu kali — perlu dilindungi dengan diversifikasi sumber pendapatan."
        ),
        business_type="kuliner",
    )


def _build_anomaly_output() -> AnomalyOutput:
    return AnomalyOutput(
        session_id=DEMO_SESSION_ID,
        anomalies=[
            Anomaly(
                category="SDM",
                severity="MEDIUM",
                current_amount=1_200_000,
                baseline_amount=750_000,
                deviation_pct=60.0,
                description="Pengeluaran gaji 60% di atas baseline industri kuliner skala kecil.",
                suggested_action="Evaluasi produktivitas karyawan — apakah output sebanding dengan gaji saat ini?",
            ),
        ],
        total_anomalies=1,
        high_severity_count=0,
        analyst_output_valid=True,
        analyst_correction=None,
        trigger_reflection=False,
        overall_risk_level="LOW",
    )


def _build_scenario_output() -> ScenarioOutput:
    return ScenarioOutput(
        session_id=DEMO_SESSION_ID,
        scenario_type="revenue_drop",
        parameter_name="revenue",
        parameter_change_pct=-20.0,
        new_runway=ConfidenceRange(
            minimum=15, expected=21, maximum=27,
            assumption="Pengeluaran tetap, pemasukan turun 20%",
        ),
        new_health_score=61.0,
        breakeven_day=21,
        cuttable_costs=[
            CostItem(category="Bahan Baku",  amount=705_000,  is_cuttable=True,  cut_potential_pct=30, rationale="Bisa kurangi porsi atau ganti supplier lebih murah"),
            CostItem(category="SDM",         amount=1_200_000,is_cuttable=True,  cut_potential_pct=20, rationale="Bisa kurangi jam lembur"),
        ],
        fixed_costs=[
            CostItem(category="Operasional", amount=500_000,  is_cuttable=False, cut_potential_pct=0,  rationale="Sewa lapak tidak bisa dikurangi dalam jangka pendek"),
        ],
        total_cuttable_amount=451_500,
        chain_of_consequences=(
            "Jika penjualan turun 20%, pemasukan harian turun dari Rp 1.13jt → Rp 903rb. "
            "Burn rate tetap Rp 343rb/hari, sehingga net daily cashflow turun dari +Rp 786rb → +Rp 560rb. "
            "Dengan saldo awal Rp 10.1jt, titik kritis tercapai di hari ke-21 jika tidak ada tindakan. "
            "Order katering (44% revenue) adalah area paling rentan — kehilangan 1 klien katering = -Rp 3.5jt."
        ),
        mitigation_steps=(
            "1. Segera hubungi klien katering lama untuk konfirmasi order bulan depan.\n"
            "2. Kurangi pembelian bahan baku 15% dengan sistem pre-order harian (hemat ~Rp 105rb/hari).\n"
            "3. Aktifkan promosi di GoFood/GrabFood untuk tingkatkan penjualan walk-in.\n"
            "4. Tunda pembelian peralatan baru hingga situasi stabil."
        ),
        mitigation_impact="Dengan mitigasi, runway kembali ke 34 hari dan health score stabil di 67/100.",
    )


def _build_advisor_output() -> AdvisorOutput:
    return AdvisorOutput(
        session_id=DEMO_SESSION_ID,
        has_early_warning=True,
        early_warning=EarlyWarning(
            message="Tanpa pemasukan baru, dana habis dalam 29 hari. Order katering tunggal mewakili 44% pendapatan — risiko konsentrasi tinggi.",
            days_until_crisis=29,
            confidence=ConfidenceRange(
                minimum=23, expected=29, maximum=37,
                assumption="Pengeluaran konstan, tidak ada pemasukan baru",
            ),
            trigger_condition="Burn rate Rp 343.571/hari dengan saldo Rp 10.095.000",
        ),
        action_items=[
            ActionItem(
                priority=1,
                title="Amankan Order Katering Berikutnya",
                description="44% pemasukan berasal dari 1 order katering. Hubungi klien minggu ini untuk konfirmasi order bulan depan. Tanpa ini, runway turun ke 15 hari.",
                urgency="IMMEDIATE",
                estimated_impact="Menambah Rp 3,5jt pendapatan = +10 hari runway",
                category="Revenue Protection",
            ),
            ActionItem(
                priority=2,
                title="Evaluasi Gaji Karyawan",
                description="Pengeluaran SDM 60% di atas baseline industri. Apakah produktivitas sebanding? Pertimbangkan sistem bonus berbasis penjualan daripada gaji tetap tinggi.",
                urgency="THIS_WEEK",
                estimated_impact="Potensi hemat Rp 200-400rb/bulan",
                category="Cost Optimization",
            ),
            ActionItem(
                priority=3,
                title="Aktifkan Platform Delivery Online",
                description="Diversifikasi dari walk-in ke GoFood/GrabFood untuk mengurangi ketergantungan katering. Target: 30% penjualan dari delivery dalam 1 bulan.",
                urgency="THIS_WEEK",
                estimated_impact="Potensi tambah Rp 500rb-1jt/minggu",
                category="Revenue Diversification",
            ),
            ActionItem(
                priority=4,
                title="Sistem Bahan Baku Pre-Order",
                description="Beli bahan baku berdasarkan estimasi pesanan esok hari, bukan stok harian. Kurangi pemborosan bahan yang tidak terjual.",
                urgency="THIS_MONTH",
                estimated_impact="Hemat 10-15% biaya bahan baku = ~Rp 70-105rb/hari",
                category="Cost Optimization",
            ),
        ],
        executive_summary=(
            "Bisnis Anda dalam kondisi SEHAT dengan Health Score 74/100 — di atas rata-rata "
            "industri kuliner. Pemasukan minggu ini Rp 7,9jt dengan net positif Rp 5,5jt. "
            "Namun ada satu risiko kritis: 44% pendapatan bergantung pada 1 order katering. "
            "Tanpa order baru, dana habis dalam 29 hari. Prioritas utama: amankan katering berikutnya."
        ),
        detailed_advice=(
            "**Kondisi Saat Ini (Positif):**\n"
            "- Health Score 74/100 — naik dari 68 bulan lalu ✅\n"
            "- Net margin 57,5% — baik untuk skala warung\n"
            "- Penjualan mingguan stabil (Sabtu+Minggu = Rp 3,9jt)\n\n"
            "**Risiko yang Perlu Diatasi:**\n"
            "- Konsentrasi pendapatan: 1 order katering = 44% total income\n"
            "- Gaji karyawan 60% di atas baseline industri\n"
            "- Runway hanya 29 hari tanpa pemasukan baru\n\n"
            "**Rencana Aksi Minggu Ini:**\n"
            "1. Senin: Hubungi klien katering untuk order berikutnya\n"
            "2. Selasa: Daftar di GoFood/GrabFood (gratis, proses 1-2 hari)\n"
            "3. Rabu: Diskusikan dengan karyawan sistem bonus penjualan\n"
            "4. Jumat: Evaluasi bahan baku yang tidak terpakai minggu ini"
        ),
        uncertainty_statement=(
            "Analisis berdasarkan transaksi 7 hari yang dimasukkan. "
            "Jika ada pengeluaran rutin lain (cicilan, pajak, dll) yang belum tercatat, "
            "runway aktual bisa lebih pendek. Angka baseline menggunakan rata-rata industri "
            "karena ini adalah analisis pertama — akan semakin akurat setelah 3 bulan data."
        ),
        conflict_detected=False,
        conflict_resolution="",
    )


# ══════════════════════════════════════════════════════════════════
# QUICK DEMO SCENARIOS — tambahan untuk presentasi
# ══════════════════════════════════════════════════════════════════

DEMO_QA_PAIRS = [
    {
        "question": "Kapan kira-kira uang saya habis?",
        "answer": (
            "Dengan saldo Rp 10,1 juta dan pengeluaran rata-rata Rp 343.571 per hari, "
            "uang akan habis sekitar **29 hari lagi** (sekitar 8 Juni) jika tidak ada "
            "pemasukan baru. Tapi ini asumsi terburuk — penjualan harian Sabtu-Minggu "
            "saja sudah Rp 3,9jt seminggu. Amankan order katering berikutnya adalah langkah paling kritis."
        ),
    },
    {
        "question": "Apa yang terjadi kalau penjualan turun 20%?",
        "answer": (
            "Jika penjualan turun 20%, runway Anda berkurang dari 29 hari → **21 hari**. "
            "Titik kritis di hari ke-21. Langkah mitigasi: kurangi beli bahan baku 15% "
            "(hemat ~Rp 105rb/hari) dan aktifkan delivery online. "
            "Dengan mitigasi, runway kembali ke 34 hari."
        ),
    },
    {
        "question": "Apakah gaji karyawan saya terlalu tinggi?",
        "answer": (
            "Gaji Rp 1,2 juta/minggu atau ~Rp 4,8 juta/bulan **60% di atas** rata-rata "
            "warung kuliner seukuran ini (baseline Rp 3jt/bulan). "
            "Ini bukan selalu masalah — jika karyawan tersebut menangani katering dan "
            "penjualan sekaligus, kontribusinya sepadan. "
            "Saran: evaluasi apakah sistem bonus penjualan lebih adil daripada gaji tetap tinggi."
        ),
    },
]
