"""
agents/advisor_agent.py
CFO Sentinel — Strategic Advisor Agent

Agent terakhir dalam pipeline. Menerima output dari SEMUA agent
sebelumnya dan menghasilkan rekomendasi strategis final.

Fitur khusus:
- Conflict resolution: jika Anomaly vs Scenario bertentangan,
  prioritaskan survival (konservatif)
- Uncertainty awareness: semua output punya confidence range
- Conversational: user bisa tanya dalam Bahasa Indonesia
"""

from core.llm_client import call_llm_json, call_llm
from core.prompts import (
    ADVISOR_SYSTEM,
    get_advisor_prompt,
    get_conversational_prompt,
)
from core.schemas import (
    AnalystOutput,
    AnomalyOutput,
    ScenarioOutput,
    AdvisorOutput,
    ActionItem,
    EarlyWarning,
    ConfidenceRange,
)
from core.memory import get_historical_context


def _build_analyst_summary(analyst: AnalystOutput) -> str:
    """Format ringkasan output Analyst untuk Advisor prompt."""
    hs = analyst.health_score
    runway = analyst.runway_days

    lines = [
        f"- Periode: {analyst.period_start} s/d {analyst.period_end}",
        f"- Total Pemasukan:   Rp {analyst.total_income:,.0f}",
        f"- Total Pengeluaran: Rp {analyst.total_expense:,.0f}",
        f"- Net Cash Flow:     Rp {analyst.net_cashflow:,.0f}",
        f"- Saldo Saat Ini:    Rp {analyst.cash_balance:,.0f}",
        f"- Burn Rate Harian:  Rp {analyst.burn_rate_daily:,.0f}",
        f"- Runway:            {runway.expected:.0f} hari "
        f"(min {runway.minimum:.0f} – max {runway.maximum:.0f})",
        f"- Gross Margin:      {analyst.gross_margin:.1f}%",
        f"- Health Score:      {hs.current:.0f}/100 "
        f"(bulan lalu: {hs.previous_month:.0f}, "
        f"industri: {hs.industry_average:.0f})",
        f"- Status:            {hs.status} | Tren: {hs.trend}",
        f"- Jenis Bisnis:      {analyst.business_type}",
        f"\nNarasi Analyst:\n{analyst.narrative}",
    ]
    return "\n".join(lines)


def _build_anomaly_summary(anomaly: AnomalyOutput) -> str:
    """Format ringkasan output Anomaly Detection untuk Advisor prompt."""
    if not anomaly.anomalies:
        return "Tidak ada anomali yang terdeteksi. Pengeluaran dalam batas normal."

    lines = [
        f"Risk Level: {anomaly.overall_risk_level}",
        f"Total anomali: {anomaly.total_anomalies} "
        f"(HIGH: {anomaly.high_severity_count})",
        "",
    ]
    for a in anomaly.anomalies:
        severity = getattr(a, 'severity', None) or (a.get('severity', '?') if isinstance(a, dict) else '?')
        category = getattr(a, 'category', None) or (a.get('category', '?') if isinstance(a, dict) else '?')
        current_amount = getattr(a, 'current_amount', None) or (a.get('current_amount', 0) if isinstance(a, dict) else 0)
        baseline_amount = getattr(a, 'baseline_amount', None) or (a.get('baseline_amount', 0) if isinstance(a, dict) else 0)
        deviation_pct = getattr(a, 'deviation_pct', None) or (a.get('deviation_pct', 0) if isinstance(a, dict) else 0)
        description = getattr(a, 'description', None) or (a.get('description', '') if isinstance(a, dict) else '')

        lines.append(
            f"[{severity}] {category}: "
            f"Rp {current_amount:,.0f} "
            f"(baseline Rp {baseline_amount:,.0f}, "
            f"deviasi {deviation_pct:+.0f}%)"
        )
        if description:
            lines.append(f"  → {description}")

    if anomaly.trigger_reflection:
        lines.append(
            f"\n⚠️  Critic flag aktif — Analyst perlu koreksi: "
            f"{anomaly.analyst_correction or 'tidak ada detail'}"
        )

    return "\n".join(lines)


def _build_scenario_summary(scenario: ScenarioOutput | None) -> str:
    """Format ringkasan output Scenario untuk Advisor prompt."""
    if scenario is None:
        return "Tidak ada simulasi skenario dalam sesi ini."

    runway = scenario.new_runway
    lines = [
        f"Skenario: {scenario.scenario_type}",
        f"Parameter: {scenario.parameter_name} {scenario.parameter_change_pct:+.0f}%",
        f"Runway baru: {runway.expected:.0f} hari "
        f"(min {runway.minimum:.0f} – max {runway.maximum:.0f})",
        f"Health Score baru: {scenario.new_health_score:.0f}/100",
    ]
    if scenario.breakeven_day:
        lines.append(f"Titik kritis: hari ke-{scenario.breakeven_day}")

    lines.append(f"\nRantai konsekuensi:\n{scenario.chain_of_consequences}")
    lines.append(f"\nLangkah mitigasi:\n{scenario.mitigation_steps}")

    if scenario.mitigation_impact:
        lines.append(f"\nDampak mitigasi: {scenario.mitigation_impact}")

    if scenario.cuttable_costs:
        total = scenario.total_cuttable_amount
        lines.append(
            f"\nBiaya yang bisa dipotong: Rp {total:,.0f} "
            f"({len(scenario.cuttable_costs)} kategori)"
        )

    return "\n".join(lines)


def _detect_conflict(
    anomaly: AnomalyOutput,
    scenario: ScenarioOutput | None,
) -> tuple[bool, str]:
    """
    Deteksi konflik antara sinyal Anomaly dan Scenario.
    Jika konflik → prioritaskan yang lebih konservatif (survival first).
    Returns (conflict_detected, resolution_message)
    """
    if scenario is None:
        return False, ""

    # Konflik: Anomaly HIGH tapi Scenario bilang runway cukup panjang
    if (
        anomaly.overall_risk_level in ("HIGH", "CRITICAL")
        and scenario.new_runway.expected > 60
    ):
        return (
            True,
            "Anomaly Agent mendeteksi risiko tinggi, namun Scenario Agent "
            "memproyeksikan runway yang panjang. Sistem memprioritaskan sinyal "
            "konservatif dari Anomaly — asumsikan kondisi lebih berisiko.",
        )

    # Konflik: Scenario runway sangat pendek tapi anomaly LOW
    if (
        anomaly.overall_risk_level == "LOW"
        and scenario.new_runway.expected < 15
    ):
        return (
            True,
            "Scenario Agent memproyeksikan runway sangat pendek, namun "
            "Anomaly Agent tidak menemukan masalah. Sistem mengikuti Scenario "
            "yang lebih pesimis — lebih baik waspada.",
        )

    return False, ""


def run_advisor_agent(
    analyst_output: AnalystOutput,
    anomaly_output: AnomalyOutput,
    scenario_output: ScenarioOutput | None = None,
) -> AdvisorOutput:
    """
    Jalankan Strategic Advisor Agent — penghasil rekomendasi final.

    Args:
        analyst_output:  Output dari Financial Analyst Agent
        anomaly_output:  Output dari Anomaly Detection Agent
        scenario_output: Output dari Scenario Agent (opsional)

    Returns:
        AdvisorOutput: Rekomendasi lengkap beserta peringatan dini
    """
    session_id    = analyst_output.session_id
    business_type = analyst_output.business_type

    # ── Bangun prompt components ───────────────────────────────────
    analyst_summary   = _build_analyst_summary(analyst_output)
    anomaly_summary   = _build_anomaly_summary(anomaly_output)
    scenario_summary  = _build_scenario_summary(scenario_output)
    historical_ctx    = get_historical_context(business_type)

    conflict_detected, conflict_resolution = _detect_conflict(
        anomaly_output, scenario_output
    )

    prompt_data = {
        "business_type":      business_type,
        "analyst_summary":    analyst_summary,
        "anomaly_summary":    anomaly_summary,
        "scenario_summary":   scenario_summary,
        "historical_context": historical_ctx,
    }

    # Jika ada konflik, inject ke prompt
    if conflict_detected:
        prompt_data["anomaly_summary"] += (
            f"\n\n⚠️  CONFLICT DETECTED: {conflict_resolution}"
        )

    user_prompt = get_advisor_prompt(prompt_data)

    # ── LLM Call ──────────────────────────────────────────────────
    parsed_json, metadata = call_llm_json(
        agent_name="advisor",
        system_prompt=ADVISOR_SYSTEM,
        user_message=user_prompt,
    )

    # ── Parse action_items ─────────────────────────────────────────
    action_items: list[ActionItem] = []
    for item in parsed_json.get("action_items", []):
        try:
            action_items.append(
                ActionItem(
                    priority=item.get("priority", 99),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    urgency=item.get("urgency", "THIS_MONTH"),
                    estimated_impact=item.get("estimated_impact", ""),
                    category=item.get("category", ""),
                )
            )
        except Exception:
            pass  # skip invalid items

    action_items.sort(key=lambda x: x.priority)

    # ── Parse early_warning ────────────────────────────────────────
    early_warning: EarlyWarning | None = None
    has_early_warning = parsed_json.get("has_early_warning", False)

    if has_early_warning and parsed_json.get("early_warning"):
        ew_data = parsed_json["early_warning"]
        conf_data = ew_data.get("confidence", {})
        try:
            early_warning = EarlyWarning(
                message=ew_data.get("message", ""),
                days_until_crisis=ew_data.get("days_until_crisis"),
                confidence=ConfidenceRange(
                    minimum=conf_data.get("minimum", 0),
                    expected=conf_data.get("expected", 0),
                    maximum=conf_data.get("maximum", 0),
                    assumption=conf_data.get("assumption", ""),
                ),
                trigger_condition=ew_data.get("trigger_condition", ""),
            )
        except Exception:
            has_early_warning = False

    # ── Build AdvisorOutput ────────────────────────────────────────
    output = AdvisorOutput(
        session_id=session_id,
        has_early_warning=has_early_warning,
        early_warning=early_warning,
        action_items=action_items,
        executive_summary=parsed_json.get(
            "executive_summary",
            "Analisis keuangan selesai. Lihat detail di bawah.",
        ),
        detailed_advice=parsed_json.get("detailed_advice", ""),
        uncertainty_statement=parsed_json.get(
            "uncertainty_statement",
            "Analisis berdasarkan data yang dimasukkan. "
            "Hasil bisa berbeda jika ada transaksi yang belum tercatat.",
        ),
        conflict_detected=conflict_detected,
        conflict_resolution=conflict_resolution,
    )

    return output


def answer_question(
    question: str,
    analyst_output: AnalystOutput,
    anomaly_output: AnomalyOutput,
    advisor_output: AdvisorOutput,
) -> str:
    """
    Jawab pertanyaan ad-hoc dari user menggunakan data sesi saat ini.
    Dipanggil dari conversational interface di dashboard.

    Args:
        question:      Pertanyaan dari user dalam BI
        analyst_output, anomaly_output, advisor_output: konteks data

    Returns:
        str: Jawaban teks dari LLM
    """
    hs = analyst_output.health_score

    financial_context = f"""
Saldo saat ini:    Rp {analyst_output.cash_balance:,.0f}
Burn rate harian:  Rp {analyst_output.burn_rate_daily:,.0f}
Runway:            {analyst_output.runway_days.expected:.0f} hari
Health Score:      {hs.current:.0f}/100 ({hs.status})
Gross Margin:      {analyst_output.gross_margin:.1f}%
Anomali ditemukan: {anomaly_output.total_anomalies} 
  (HIGH: {anomaly_output.high_severity_count})
Risk Level:        {anomaly_output.overall_risk_level}

Rekomendasi utama:
{analyst_output.narrative}

Early Warning: {advisor_output.early_warning.message if advisor_output.early_warning else 'Tidak ada'}
""".strip()

    system_prompt = get_conversational_prompt(financial_context)

    response, _ = call_llm(
        agent_name="advisor",
        system_prompt=system_prompt,
        user_message=question,
        response_format="text",
    )

    return response or "Maaf, saya tidak dapat menjawab pertanyaan itu saat ini."
