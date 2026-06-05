"""
agents/anomaly_agent.py
CFO Sentinel — Anomaly Detection Agent

Deteksi pengeluaran abnormal + validasi output Analyst (Critic Pattern).
Bisa trigger reflection loop (max 2x) jika ada inkonsistensi.
"""

from core.llm_client import call_llm_json
from core.prompts import ANOMALY_SYSTEM, get_anomaly_prompt
from core.schemas import AnalystOutput, CategorizerOutput, AnomalyOutput
from core.memory import load_baselines_for_analysis


def _safe_get(obj, key, default=None):
    """Safely get attribute from Pydantic model or dict."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def run_anomaly_agent(
    analyst_output: AnalystOutput,
    categorizer_output: CategorizerOutput,
    business_type: str = "general"
) -> AnomalyOutput:
    
    # Hitung pengeluaran per kategori — handle Pydantic dan dict
    current_spending = []
    for c in categorizer_output.categories_found:
        total = sum(
            _safe_get(t, "amount", 0)
            for t in categorizer_output.transactions
            if _safe_get(t, "category") == c and _safe_get(t, "type") == "expense"
        )
        if total > 0:
            current_spending.append({"category": c, "total": total})

    # Dapatkan 5 transaksi pengeluaran terbesar untuk Micro Anomaly Detection
    expenses = [
        t for t in categorizer_output.transactions
        if _safe_get(t, "type") == "expense"
    ]
    expenses_sorted = sorted(expenses, key=lambda x: _safe_get(x, "amount", 0), reverse=True)
    largest_transactions = []
    for t in expenses_sorted[:5]:
        largest_transactions.append({
            "date": _safe_get(t, "date"),
            "description": _safe_get(t, "description"),
            "amount": _safe_get(t, "amount", 0),
            "category": _safe_get(t, "category")
        })
            
    baselines = load_baselines_for_analysis(business_type)
    
    prompt_data = {
        "current_spending": current_spending,
        "largest_transactions": largest_transactions,
        "baseline_data": baselines,
        "runway_days": analyst_output.runway_days.expected,
        "health_score": analyst_output.health_score.current,
        "analyst_narrative": analyst_output.narrative
    }
    
    prompt = get_anomaly_prompt(prompt_data)
    
    try:
        parsed_json, _ = call_llm_json(
            agent_name="anomaly",
            system_prompt=CFO_SYSTEM,
            user_message=prompt
        )
    except Exception:
        parsed_json = {}

    if not parsed_json:
        baseline_map = {b["category"]: b for b in baselines}
        fallback_anomalies = []
        for item in current_spending:
            category = item["category"]
            current = item["total"]
            baseline = baseline_map.get(category, {})
            avg = baseline.get("avg_monthly", 0) or 0
            if avg <= 0:
                continue
            deviation = ((current - avg) / avg) * 100
            abs_dev = abs(deviation)
            if abs_dev < 50:
                continue
            severity = "HIGH" if abs_dev >= 100 else "MEDIUM"
            fallback_anomalies.append({
                "category": category,
                "severity": severity,
                "current_amount": current,
                "baseline_amount": avg,
                "deviation_pct": round(deviation, 1),
                "description": (
                    f"{category} menyimpang {abs_dev:.0f}% dari baseline "
                    f"Rp {avg:,.0f}."
                ),
                "suggested_action": "Cek bukti transaksi dan validasi apakah biaya ini memang perlu.",
            })
        parsed_json = {
            "anomalies": fallback_anomalies,
            "analyst_output_valid": True,
            "trigger_reflection": False,
            "overall_risk_level": (
                "HIGH" if any(a["severity"] == "HIGH" for a in fallback_anomalies)
                else "MEDIUM" if fallback_anomalies
                else "LOW"
            ),
        }
    
    anomalies = parsed_json.get("anomalies", [])
    high_severity_count = sum(1 for a in anomalies if a.get("severity") == "HIGH")
    
    output = AnomalyOutput(
        session_id=analyst_output.session_id,
        anomalies=anomalies,
        total_anomalies=len(anomalies),
        high_severity_count=high_severity_count,
        analyst_output_valid=parsed_json.get("analyst_output_valid", True),
        analyst_correction=parsed_json.get("analyst_correction"),
        trigger_reflection=parsed_json.get("trigger_reflection", False),
        overall_risk_level=parsed_json.get("overall_risk_level", "LOW")
    )
    
    return output
