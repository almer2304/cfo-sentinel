"""
agents/scenario_agent.py
CFO Sentinel — Scenario Simulation Agent

Simulasi "what if" dengan deep reasoning.
Bukan sekedar kalkulator — harus reason tentang fixed vs variable cost,
chain of consequences, titik kritis, dan mitigasi konkret.
"""

from core.llm_client import call_llm_json
from core.prompts import SCENARIO_SYSTEM, get_scenario_prompt
from core.schemas import AnalystOutput, CategorizerOutput, ScenarioOutput, ConfidenceRange


def _safe_get(obj, key, default=None):
    """Safely get attribute from Pydantic model or dict."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def run_scenario_agent(
    analyst_output: AnalystOutput,
    categorizer_output: CategorizerOutput,
    scenario_description: str,
    parameter_name: str,
    parameter_change_pct: float
) -> ScenarioOutput:
    
    # Hitung expense breakdown — handle Pydantic dan dict
    expense_breakdown = []
    for c in categorizer_output.categories_found:
        txs = [
            t for t in categorizer_output.transactions
            if _safe_get(t, "category") == c and _safe_get(t, "type") == "expense"
        ]
        total = sum(_safe_get(t, "amount", 0) for t in txs)
        is_recurring = any(_safe_get(t, "is_recurring", False) for t in txs)
        if total > 0:
            expense_breakdown.append({
                "category": c,
                "total": total,
                "is_recurring": is_recurring
            })
            
    prompt_data = {
        "cash_balance": analyst_output.cash_balance,
        "burn_rate_daily": analyst_output.burn_rate_daily,
        "runway_days": analyst_output.runway_days.expected,
        "health_score": analyst_output.health_score.current,
        "expense_breakdown": expense_breakdown,
        "scenario_description": scenario_description,
        "parameter_name": parameter_name,
        "parameter_change_pct": parameter_change_pct
    }
    
    prompt = get_scenario_prompt(prompt_data)
    
    parsed_json, metadata = call_llm_json(
        agent_name="scenario",
        system_prompt=SCENARIO_SYSTEM,
        user_message=prompt
    )
    
    new_runway_data = parsed_json.get("new_runway", {})
    new_runway = ConfidenceRange(
        minimum=new_runway_data.get("minimum", 0),
        expected=new_runway_data.get("expected", 0),
        maximum=new_runway_data.get("maximum", 0),
        assumption=new_runway_data.get("assumption", "")
    )
    
    output = ScenarioOutput(
        session_id=analyst_output.session_id,
        scenario_type=parsed_json.get("scenario_type", "custom"),
        parameter_name=parsed_json.get("parameter_name", parameter_name),
        parameter_change_pct=parsed_json.get("parameter_change_pct", parameter_change_pct),
        new_runway=new_runway,
        new_health_score=parsed_json.get("new_health_score", analyst_output.health_score.current),
        breakeven_day=parsed_json.get("breakeven_day"),
        cuttable_costs=parsed_json.get("cuttable_costs", []),
        fixed_costs=parsed_json.get("fixed_costs", []),
        total_cuttable_amount=parsed_json.get("total_cuttable_amount", 0),
        chain_of_consequences=parsed_json.get("chain_of_consequences", ""),
        mitigation_steps=parsed_json.get("mitigation_steps", ""),
        mitigation_impact=parsed_json.get("mitigation_impact", "")
    )
    
    return output
