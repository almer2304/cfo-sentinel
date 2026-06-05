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
    
    try:
        parsed_json, _ = call_llm_json(
            agent_name="scenario",
            system_prompt=CFO_SYSTEM,
            user_message=prompt
        )
    except Exception:
        parsed_json = {}

    if not parsed_json:
        monthly_income = analyst_output.total_income or analyst_output.journal_revenue
        monthly_expense = analyst_output.burn_rate_monthly or analyst_output.total_expense
        delta = monthly_income * (parameter_change_pct / 100)
        projected_income = max(0, monthly_income + delta)
        projected_monthly_net = projected_income - monthly_expense
        projected_daily_cash_burn = max((monthly_expense - projected_income) / 30, 0)
        if analyst_output.cash_balance <= 0:
            projected_runway = 0
        elif projected_daily_cash_burn > 0:
            projected_runway = analyst_output.cash_balance / projected_daily_cash_burn
        else:
            projected_runway = 180
        projected_runway = max(0, min(projected_runway, 180))
        cuttable = [
            {
                "category": item["category"],
                "amount": item["total"],
                "is_cuttable": not item["is_recurring"],
                "cut_potential_pct": 30 if not item["is_recurring"] else 10,
                "rationale": "Biaya non-rutin lebih mudah dipotong cepat." if not item["is_recurring"] else "Biaya rutin perlu negosiasi atau pengurangan bertahap.",
            }
            for item in expense_breakdown
        ]
        total_cuttable = sum(
            item["amount"] * (item["cut_potential_pct"] / 100)
            for item in cuttable
        )
        parsed_json = {
            "scenario_type": "revenue_drop" if parameter_change_pct < 0 else "revenue_change",
            "parameter_name": parameter_name,
            "parameter_change_pct": parameter_change_pct,
            "new_runway": {
                "minimum": projected_runway * 0.8,
                "expected": projected_runway,
                "maximum": projected_runway * 1.2,
                "assumption": "Simulasi deterministik dari perubahan pendapatan dan burn rate saat ini.",
            },
            "new_health_score": max(0, min(100, analyst_output.health_score.current + (parameter_change_pct * 0.5))),
            "breakeven_day": int(projected_runway) if projected_monthly_net < 0 else None,
            "cuttable_costs": [item for item in cuttable if item["is_cuttable"]],
            "fixed_costs": [item for item in cuttable if not item["is_cuttable"]],
            "total_cuttable_amount": total_cuttable,
            "chain_of_consequences": (
                f"Jika {parameter_name} berubah {parameter_change_pct:+.0f}%, arus kas bulanan "
                f"berubah sekitar Rp {delta:,.0f}. Runway diproyeksikan menjadi "
                f"{projected_runway:.0f} hari."
            ),
            "mitigation_steps": "Prioritaskan penagihan kas masuk, kurangi biaya non-rutin, dan negosiasikan biaya tetap terbesar.",
            "mitigation_impact": f"Potensi penghematan cepat sekitar Rp {total_cuttable:,.0f}.",
        }
    
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
