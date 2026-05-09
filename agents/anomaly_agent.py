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
            
    baselines = load_baselines_for_analysis(business_type)
    
    prompt_data = {
        "current_spending": current_spending,
        "baseline_data": baselines,
        "runway_days": analyst_output.runway_days.expected,
        "health_score": analyst_output.health_score.current,
        "analyst_narrative": analyst_output.narrative
    }
    
    prompt = get_anomaly_prompt(prompt_data)
    
    parsed_json, metadata = call_llm_json(
        agent_name="anomaly",
        system_prompt=ANOMALY_SYSTEM,
        user_message=prompt
    )
    
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
