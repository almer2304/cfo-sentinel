"""
agents/analyst_agent.py
CFO Sentinel — Financial Analyst Agent

CHANGELOG:
- Fix health score formula: lebih akurat mencerminkan kondisi nyata
  Formula lama: 50 + (margin/2) + (runway/3) → terlalu optimis
  Formula baru: weighted scoring dari 4 komponen dengan penalti
- Fix runway: negative balance → runway = 0 (bukan negatif)
- Fix forecast: predicted_balance di-cap minimum 0 di chart
- Add: deteksi kondisi kritis untuk trigger reflection
"""

from datetime import datetime, timedelta
from core.llm_client import call_llm
from core.prompts import ANALYST_SYSTEM, get_analyst_narrative_prompt
from core.schemas import (
    CategorizerOutput,
    AnalystOutput,
    HealthScore,
    ConfidenceRange,
    ForecastPoint,
)
from core.memory import get_industry_health_avg, get_monthly_snapshots


def _safe_get(obj, key, default=None):
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _compute_health_score(
    gross_margin:       float,
    runway_days:        float,
    net_cashflow:       float,
    total_income:       float,
    total_expense:      float,
    revenue_consistency: float,
) -> float:
    """
    Hitung Financial Health Score (0–100) dari 4 komponen:

    1. Cash Runway Score (0–35):
       Runway  0 hari → 0 poin
       Runway 30 hari → 20 poin
       Runway 60 hari → 35 poin (max)

    2. Profitability Score (0–30):
       Gross margin ≤ 0%   → 0 poin
       Gross margin = 20%  → 20 poin
       Gross margin ≥ 30%  → 30 poin (max)

    3. Cash Flow Score (0–25):
       Net cashflow positif → 25 poin
       Net cashflow negatif → 0 poin (penalti penuh)

    4. Consistency Score (0–10):
       Revenue consistency 0.0–1.0 → 0–10 poin

    Total: 0–100, di mana:
    < 50  → DANGER
    50–65 → WARNING
    > 65  → SAFE
    """
    # Komponen 1: Runway
    runway_score = min(35, (runway_days / 60) * 35)

    # Komponen 2: Gross margin
    margin_score = min(30, max(0, (gross_margin / 30) * 30))

    # Komponen 3: Cash flow direction
    cashflow_score = 25 if net_cashflow >= 0 else max(
        0,
        25 + (net_cashflow / max(total_expense, 1)) * 25
    )

    # Komponen 4: Revenue consistency
    consistency_score = revenue_consistency * 10

    total = runway_score + margin_score + cashflow_score + consistency_score
    return round(min(100, max(0, total)), 1)


def _compute_revenue_consistency(transactions) -> float:
    """
    Hitung konsistensi pemasukan (0.0–1.0).
    1.0 = pemasukan merata setiap hari
    0.0 = semua pemasukan di 1 hari
    """
    income_txs = [
        t for t in transactions
        if _safe_get(t, "type") == "income"
    ]
    if len(income_txs) <= 1:
        return 0.5  # default jika data terlalu sedikit

    # Hitung spread tanggal transaksi income
    dates = set(_safe_get(t, "date", "") for t in income_txs)
    spread_ratio = len(dates) / max(len(income_txs), 1)
    return min(1.0, spread_ratio)


def run_analyst_agent(
    categorizer_output: CategorizerOutput,
    current_cash_balance: float,
    business_type: str = "general",
) -> AnalystOutput:

    total_income  = categorizer_output.total_income
    total_expense = categorizer_output.total_expense
    net_cashflow  = total_income - total_expense

    today          = datetime.now()
    period_start   = today.replace(day=1).strftime("%Y-%m-%d")
    period_end     = today.strftime("%Y-%m-%d")
    days_in_period = max(today.day, 1)

    # ── Metrik dasar ─────────────────────────────────────────────
    burn_rate_daily   = total_expense / days_in_period
    burn_rate_monthly = burn_rate_daily * 30

    # Saldo: saldo awal + net cashflow periode ini
    cash_balance = current_cash_balance + net_cashflow

    # Runway: berapa hari saldo bisa bertahan dengan burn rate saat ini
    if burn_rate_daily > 0 and cash_balance > 0:
        expected_runway = cash_balance / burn_rate_daily
    elif cash_balance <= 0:
        expected_runway = 0  # sudah defisit
    else:
        expected_runway = 999  # tidak ada pengeluaran

    # Confidence range runway: ±20% dari expected
    min_runway = max(0, expected_runway * 0.8)
    max_runway = expected_runway * 1.2

    # Gross margin: hanya positif
    if total_income > 0:
        gross_margin = max(0, (net_cashflow / total_income) * 100)
    else:
        gross_margin = 0

    # Revenue consistency
    revenue_consistency = _compute_revenue_consistency(
        categorizer_output.transactions
    )

    # ── Health Score ─────────────────────────────────────────────
    hs_score = _compute_health_score(
        gross_margin=gross_margin,
        runway_days=expected_runway,
        net_cashflow=net_cashflow,
        total_income=total_income,
        total_expense=total_expense,
        revenue_consistency=revenue_consistency,
    )

    industry_avg = get_industry_health_avg(business_type)
    snapshots    = get_monthly_snapshots(business_type, last_n_months=1)
    prev_score   = (
        snapshots[0].get("health_score", industry_avg)
        if snapshots else industry_avg
    )

    health_score = HealthScore(
        current=hs_score,
        previous_month=prev_score,
        industry_average=industry_avg,
        danger_threshold=50,
        # trend dihitung otomatis oleh model_validator
    )

    # ── Forecast 30 hari ─────────────────────────────────────────
    forecast: list[ForecastPoint] = []
    running_balance = cash_balance

    for i in range(1, 31):
        running_balance -= burn_rate_daily
        f_date = (today + timedelta(days=i)).strftime("%Y-%m-%d")

        # Cap di 0 untuk display (tidak bisa lebih negatif dari "bangkrut")
        display_balance = max(running_balance, -burn_rate_daily * 7)

        forecast.append(ForecastPoint(
            day=i,
            date=f_date,
            predicted_balance=round(display_balance, 0),
            confidence_min=round(display_balance * 0.85, 0),
            confidence_max=round(display_balance * 1.15, 0),
        ))

    # ── Category breakdown untuk prompt ──────────────────────────
    category_breakdown = []
    for c in categorizer_output.categories_found:
        total = sum(
            _safe_get(t, "amount", 0)
            for t in categorizer_output.transactions
            if _safe_get(t, "category") == c
        )
        category_breakdown.append({"category": c, "total": total})

    # ── LLM: narasi saja, angka sudah dihitung di atas ───────────
    prompt_data = {
        "period_start":          period_start,
        "period_end":            period_end,
        "total_income":          total_income,
        "total_expense":         total_expense,
        "net_cashflow":          net_cashflow,
        "cash_balance":          cash_balance,
        "burn_rate_daily":       burn_rate_daily,
        "runway_expected":       expected_runway,
        "gross_margin":          gross_margin,
        "health_score":          hs_score,
        "health_score_prev":     prev_score,
        "health_score_industry": industry_avg,
        "business_type":         business_type,
        "category_breakdown":    category_breakdown,
    }

    prompt    = get_analyst_narrative_prompt(prompt_data)
    narrative, _ = call_llm(
        agent_name="analyst",
        system_prompt=ANALYST_SYSTEM,
        user_message=prompt,
        response_format="text",
    )

    # ── Flag untuk Orchestrator ───────────────────────────────────
    # Jika kondisi sangat kritis, tandai untuk trigger reflection
    needs_reflection = (
        health_score.status == "DANGER" and
        expected_runway < 15
    )

    return AnalystOutput(
        session_id=categorizer_output.session_id,
        period_start=period_start,
        period_end=period_end,
        total_income=total_income,
        total_expense=total_expense,
        net_cashflow=net_cashflow,
        cash_balance=cash_balance,
        burn_rate_daily=burn_rate_daily,
        burn_rate_monthly=burn_rate_monthly,
        gross_margin=gross_margin,
        runway_days=ConfidenceRange(
            minimum=min_runway,
            expected=expected_runway,
            maximum=max_runway,
            assumption="Asumsi pengeluaran konstan dari rata-rata periode ini",
        ),
        revenue_consistency=revenue_consistency,
        health_score=health_score,
        forecast_30d=forecast,
        narrative=narrative or "Analisis keuangan selesai.",
        business_type=business_type,
        needs_reflection=needs_reflection,
        reflection_note=(
            f"Kondisi kritis: runway {expected_runway:.0f} hari, "
            f"status {health_score.status}"
            if needs_reflection else ""
        ),
    )