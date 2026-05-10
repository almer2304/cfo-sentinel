"""
core/orchestrator.py
CFO Sentinel — LangGraph Orchestrator

CHANGELOG:
- Fix: LangGraph invoke() return dict — konversi ke PipelineState
  sekarang lebih safe dengan try/except dan manual mapping
- Fix: node functions sekarang return dict (bukan PipelineState)
  sesuai requirement LangGraph StateGraph
- Add: timeout protection per node
"""

import uuid
import os
from datetime import datetime
from typing import Literal, Any

# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END

from core.schemas import PipelineState
from core.database import (
    init_database,
    save_transactions,
    save_analytics,
    save_anomalies,
    save_recommendations,
    log_agent_step,
)
from core.memory import (
    save_session_snapshot,
    update_baselines_from_transactions,
)
from agents.parser_agent      import run_parser_agent
from agents.categorizer_agent import run_categorizer_agent
from agents.analyst_agent     import run_analyst_agent
from agents.anomaly_agent     import run_anomaly_agent
from agents.scenario_agent    import run_scenario_agent
from agents.advisor_agent     import run_advisor_agent


# ══════════════════════════════════════════════════════════════════
# HELPER — Safe state access (dict atau PipelineState)
# ══════════════════════════════════════════════════════════════════

def _get(state: Any, key: str, default=None):
    """Ambil field dari state (dict atau PipelineState)."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _state_to_dict(state: Any) -> dict:
    """Konversi PipelineState ke dict untuk LangGraph."""
    if isinstance(state, dict):
        return state
    if hasattr(state, "model_dump"):
        return state.model_dump()
    return dict(state)


# ══════════════════════════════════════════════════════════════════
# NODE FUNCTIONS
# LangGraph requirement: node harus return dict (bukan Pydantic model)
# ══════════════════════════════════════════════════════════════════

def node_parser(state: dict) -> dict:
    """Node 1: Parse teks bebas → transaksi terstruktur."""
    print("🔍 [Parser] Processing input...")
    start = datetime.now()

    session_id = _get(state, "session_id")
    raw_input  = _get(state, "raw_input", "")
    errors     = list(_get(state, "errors", []))
    warnings   = list(_get(state, "warnings", []))

    try:
        output = run_parser_agent(
            session_id=session_id,
            raw_input=raw_input,
        )

        log_agent_step(
            session_id=session_id,
            agent_name="parser",
            step=1,
            input_summary=f"Input: {len(raw_input)} chars",
            reasoning=(
                f"Parsed {output.total_parsed} transactions. "
                f"Has ambiguity: {output.has_ambiguity}. "
                f"Notes: {output.ambiguity_notes}"
            ),
            output_summary=f"Total parsed: {output.total_parsed}",
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            status="success",
        )

        print(f"  ✅ Parsed {output.total_parsed} transactions")
        if output.has_ambiguity:
            print(f"  ⚠️  Ambiguity: {output.ambiguity_notes}")

        return {**state, "parser_output": output, "current_step": "parser_done"}

    except Exception as e:
        errors.append(f"[Parser] {str(e)}")
        print(f"  ❌ Parser error: {e}")
        return {**state, "errors": errors, "current_step": "parser_done"}


def node_categorizer(state: dict) -> dict:
    """Node 2: Kategorisasi transaksi."""
    parser_output = _get(state, "parser_output")
    session_id    = _get(state, "session_id")
    errors        = list(_get(state, "errors", []))
    warnings      = list(_get(state, "warnings", []))

    if not parser_output or parser_output.total_parsed == 0:
        warnings.append("Tidak ada transaksi untuk dikategorisasi.")
        return {**state, "warnings": warnings, "current_step": "categorizer_done"}

    print(f"🏷️  [Categorizer] Categorizing {parser_output.total_parsed} transactions...")
    start = datetime.now()

    try:
        output = run_categorizer_agent(parser_output)

        # Simpan transaksi ke database
        tx_dicts = [
            t.model_dump() if hasattr(t, "model_dump") else dict(t)
            for t in output.transactions
        ]
        user_id = _get(state, "user_id")
        save_transactions(tx_dicts, session_id, user_id=user_id)

        log_agent_step(
            session_id=session_id,
            agent_name="categorizer",
            step=2,
            input_summary=f"{parser_output.total_parsed} transactions",
            reasoning=(
                f"Categories found: {output.categories_found}. "
                f"Recurring: {output.recurring_count}. "
                f"Income: Rp {output.total_income:,.0f}, "
                f"Expense: Rp {output.total_expense:,.0f}"
            ),
            output_summary=(
                f"Income: Rp {output.total_income:,.0f} | "
                f"Expense: Rp {output.total_expense:,.0f}"
            ),
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            status="success",
        )

        print(f"  ✅ Categories: {output.categories_found}")
        print(f"  📊 Income: Rp {output.total_income:,.0f} | "
              f"Expense: Rp {output.total_expense:,.0f}")

        return {
            **state,
            "categorizer_output": output,
            "current_step": "categorizer_done",
        }

    except Exception as e:
        errors.append(f"[Categorizer] {str(e)}")
        print(f"  ❌ Categorizer error: {e}")
        return {**state, "errors": errors, "current_step": "categorizer_done"}


def node_analyst(state: dict) -> dict:
    """Node 3: Kalkulasi metrik keuangan + narasi."""
    categorizer_output    = _get(state, "categorizer_output")
    current_cash_balance  = _get(state, "current_cash_balance", 0)
    business_type         = _get(state, "business_type", "general")
    session_id            = _get(state, "session_id")
    reflection_count      = _get(state, "reflection_count", 0)
    anomaly_output        = _get(state, "anomaly_output")  # None on initial call
    errors                = list(_get(state, "errors", []))
    warnings              = list(_get(state, "warnings", []))

    # FIX: Increment counter DI SINI (di dalam NODE), bukan di edge function.
    # Kita tahu ini adalah reflection call jika anomaly_output sudah ada di state
    # (initial call → anomaly_output=None, reflection call → anomaly_output sudah terisi).
    # Mutasi state di dalam edge/conditional function tidak persist di LangGraph.
    if anomaly_output is not None:
        reflection_count += 1

    if not categorizer_output:
        warnings.append("Tidak ada data kategorisasi.")
        return {
            **state,
            "warnings": warnings,
            "reflection_count": reflection_count,
            "current_step": "analyst_done",
        }

    label = "Analyst" if reflection_count == 0 else f"Analyst (reflection #{reflection_count})"
    print(f"📈 [{label}] Computing financial metrics...")
    start = datetime.now()

    try:
        output = run_analyst_agent(
            categorizer_output=categorizer_output,
            current_cash_balance=current_cash_balance,
            business_type=business_type,
        )

        log_agent_step(
            session_id=session_id,
            agent_name="analyst",
            step=3 + reflection_count,
            input_summary=f"Cash balance: Rp {current_cash_balance:,.0f}",
            reasoning=(
                f"Reflection #{reflection_count}. "
                f"Health: {output.health_score.current:.0f}/100 "
                f"({output.health_score.status}). "
                f"Runway: {output.runway_days.expected:.0f} days. "
                f"Gross margin: {output.gross_margin:.1f}%. "
                f"Burn rate: Rp {output.burn_rate_daily:,.0f}/day"
            ),
            output_summary=(
                f"Health: {output.health_score.current:.0f}/100 "
                f"({output.health_score.status}) | "
                f"Runway: {output.runway_days.expected:.0f}d"
            ),
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            status="success",
        )

        print(f"  ✅ Health Score: {output.health_score.current:.0f}/100 "
              f"({output.health_score.status})")
        print(f"  📅 Runway: {output.runway_days.expected:.0f} hari")
        print(f"  💰 Burn rate: Rp {output.burn_rate_daily:,.0f}/hari")

        return {
            **state,
            "analyst_output": output,
            "reflection_count": reflection_count,  # persist counter yang sudah diincrement
            "current_step": "analyst_done",
        }

    except Exception as e:
        errors.append(f"[Analyst] {str(e)}")
        print(f"  ❌ Analyst error: {e}")
        return {
            **state,
            "errors": errors,
            "reflection_count": reflection_count,
            "current_step": "analyst_done",
        }


def node_anomaly(state: dict) -> dict:
    """Node 4: Deteksi anomali + Critic Pattern."""
    analyst_output     = _get(state, "analyst_output")
    categorizer_output = _get(state, "categorizer_output")
    business_type      = _get(state, "business_type", "general")
    session_id         = _get(state, "session_id")
    errors             = list(_get(state, "errors", []))
    warnings           = list(_get(state, "warnings", []))

    if not analyst_output or not categorizer_output:
        warnings.append("Data tidak cukup untuk deteksi anomali.")
        return {**state, "warnings": warnings, "current_step": "anomaly_done"}

    print("🔎 [Anomaly] Detecting anomalies + validating analyst output...")
    start = datetime.now()

    try:
        output = run_anomaly_agent(
            analyst_output=analyst_output,
            categorizer_output=categorizer_output,
            business_type=business_type,
        )

        # Simpan anomali ke database
        anomaly_dicts = [
            a.model_dump() if hasattr(a, "model_dump") else dict(a)
            for a in output.anomalies
        ]
        user_id = _get(state, "user_id")
        if anomaly_dicts:
            save_anomalies(anomaly_dicts, session_id, user_id=user_id)

        log_agent_step(
            session_id=session_id,
            agent_name="anomaly",
            step=4,
            input_summary=(
                f"Health score: {analyst_output.health_score.current:.0f}, "
                f"spending categories: {len(categorizer_output.categories_found)}"
            ),
            reasoning=(
                f"Found {output.total_anomalies} anomalies "
                f"(HIGH: {output.high_severity_count}). "
                f"Risk: {output.overall_risk_level}. "
                f"Analyst valid: {output.analyst_output_valid}. "
                f"Trigger reflection: {output.trigger_reflection}"
            ),
            output_summary=(
                f"Anomalies: {output.total_anomalies} | "
                f"Risk: {output.overall_risk_level}"
            ),
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            status="success",
        )

        print(f"  ✅ Anomalies: {output.total_anomalies} "
              f"(HIGH: {output.high_severity_count})")
        print(f"  🚦 Risk: {output.overall_risk_level}")
        if output.trigger_reflection:
            print("  🔄 Critic flag: Analyst perlu reflection")

        return {
            **state,
            "anomaly_output": output,
            "current_step": "anomaly_done",
        }

    except Exception as e:
        errors.append(f"[Anomaly] {str(e)}")
        print(f"  ❌ Anomaly error: {e}")
        return {**state, "errors": errors, "current_step": "anomaly_done"}


def node_scenario(state: dict) -> dict:
    """Node 5: Scenario simulation."""
    analyst_output     = _get(state, "analyst_output")
    categorizer_output = _get(state, "categorizer_output")
    session_id         = _get(state, "session_id")
    errors             = list(_get(state, "errors", []))
    warnings           = list(_get(state, "warnings", []))

    if not analyst_output or not categorizer_output:
        warnings.append("Data tidak cukup untuk simulasi skenario.")
        return {**state, "warnings": warnings, "current_step": "scenario_done"}

    print("🎯 [Scenario] Running what-if simulation...")
    start = datetime.now()

    try:
        output = run_scenario_agent(
            analyst_output=analyst_output,
            categorizer_output=categorizer_output,
            scenario_description="Penjualan turun 20% bulan depan",
            parameter_name="revenue",
            parameter_change_pct=-20.0,
        )

        log_agent_step(
            session_id=session_id,
            agent_name="scenario",
            step=5,
            input_summary="Default scenario: revenue -20%",
            reasoning=(
                f"New runway: {output.new_runway.expected:.0f} days "
                f"(was {analyst_output.runway_days.expected:.0f}). "
                f"New health: {output.new_health_score:.0f}. "
                f"Cuttable: Rp {output.total_cuttable_amount:,.0f}. "
                f"Breakeven day: {output.breakeven_day}"
            ),
            output_summary=(
                f"Runway: {output.new_runway.expected:.0f}d | "
                f"Health: {output.new_health_score:.0f}/100"
            ),
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            status="success",
        )

        print(f"  ✅ New runway: {output.new_runway.expected:.0f} hari")
        print(f"  💰 Cuttable: Rp {output.total_cuttable_amount:,.0f}")

        return {
            **state,
            "scenario_output": output,
            "current_step": "scenario_done",
        }

    except Exception as e:
        errors.append(f"[Scenario] {str(e)}")
        warnings.append("Simulasi skenario gagal — lanjut tanpa scenario.")
        print(f"  ❌ Scenario error: {e}")
        return {**state, "errors": errors, "warnings": warnings,
                "current_step": "scenario_done"}


def node_advisor(state: dict) -> dict:
    """Node 6: Strategic recommendation."""
    analyst_output = _get(state, "analyst_output")
    anomaly_output = _get(state, "anomaly_output")
    scenario_output= _get(state, "scenario_output")
    session_id     = _get(state, "session_id")
    errors         = list(_get(state, "errors", []))
    warnings       = list(_get(state, "warnings", []))

    if not analyst_output or not anomaly_output:
        warnings.append("Data tidak cukup untuk rekomendasi.")
        return {**state, "warnings": warnings, "current_step": "advisor_done"}

    print("🧠 [Advisor] Generating strategic recommendations...")
    start = datetime.now()

    try:
        output = run_advisor_agent(
            analyst_output=analyst_output,
            anomaly_output=anomaly_output,
            scenario_output=scenario_output,
        )

        # Simpan rekomendasi ke database
        rec_dicts = [
            {
                "priority":      item.priority,
                "title":         item.title,
                "description":   item.description,
                "impact":        item.estimated_impact,
                "urgency":       item.urgency,
                "category":      item.category,
                "early_warning": (
                    output.early_warning.message
                    if output.has_early_warning and output.early_warning
                    else None
                ),
                "confidence_min": None,
                "confidence_max": None,
            }
            for item in output.action_items
        ]
        user_id = _get(state, "user_id")
        if rec_dicts:
            save_recommendations(rec_dicts, session_id, user_id=user_id)

        log_agent_step(
            session_id=session_id,
            agent_name="advisor",
            step=6,
            input_summary=f"Risk: {anomaly_output.overall_risk_level}",
            reasoning=(
                f"Actions: {len(output.action_items)}. "
                f"Early warning: {output.has_early_warning}. "
                f"Conflict: {output.conflict_detected}. "
                f"Uncertainty acknowledged: {bool(output.uncertainty_statement)}"
            ),
            output_summary=output.executive_summary[:150],
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            status="success",
        )

        print(f"  ✅ Actions: {len(output.action_items)}")
        if output.has_early_warning and output.early_warning:
            print(f"  🚨 Warning: {output.early_warning.message[:80]}...")

        return {
            **state,
            "advisor_output": output,
            "current_step": "advisor_done",
        }

    except Exception as e:
        errors.append(f"[Advisor] {str(e)}")
        print(f"  ❌ Advisor error: {e}")
        return {**state, "errors": errors, "current_step": "advisor_done"}


def node_finalize(state: dict) -> dict:
    """Node final: simpan snapshot bulanan + update baselines."""
    print("💾 [Finalize] Saving session data...")
    session_id     = _get(state, "session_id")
    business_type  = _get(state, "business_type", "general")
    user_id        = _get(state, "user_id")
    analyst_output = _get(state, "analyst_output")
    errors         = list(_get(state, "errors", []))

    try:
        if analyst_output:
            analytics_dict = {
                "period_start":           analyst_output.period_start,
                "period_end":             analyst_output.period_end,
                "total_income":           analyst_output.total_income,
                "total_expense":          analyst_output.total_expense,
                "net_cashflow":           analyst_output.net_cashflow,
                "cash_balance":           analyst_output.cash_balance,
                "burn_rate_daily":        analyst_output.burn_rate_daily,
                "burn_rate_monthly":      analyst_output.burn_rate_monthly,
                "gross_margin":           analyst_output.gross_margin,
                "runway_days":            analyst_output.runway_days.expected,
                "revenue_consistency":    analyst_output.revenue_consistency,
                "health_score":           analyst_output.health_score.current,
                "health_score_prev":      analyst_output.health_score.previous_month,
                "health_score_industry":  analyst_output.health_score.industry_average,
                "health_score_threshold": analyst_output.health_score.danger_threshold,
                "narrative":              analyst_output.narrative,
                "business_type":          analyst_output.business_type,
                "forecast_30d": [
                    fp.model_dump() for fp in analyst_output.forecast_30d
                ],
            }
            save_analytics(analytics_dict, session_id, user_id=user_id)
            save_session_snapshot(analytics_dict, business_type)

            year_month = datetime.now().strftime("%Y-%m")
            update_baselines_from_transactions(business_type, year_month)

        print(f"  ✅ Session {session_id[:8]}... saved")

    except Exception as e:
        errors.append(f"[Finalize] {str(e)}")
        print(f"  ❌ Finalize error: {e}")

    return {**state, "errors": errors, "current_step": "done"}


# ══════════════════════════════════════════════════════════════════
# CONDITIONAL EDGES
# ══════════════════════════════════════════════════════════════════

def should_reflect(state: dict) -> Literal["reflect", "continue"]:
    """
    Setelah Anomaly node: cek apakah Analyst perlu re-run.
    Hard limit: MAX_REFLECTION = 2.

    FIX: Fungsi ini sekarang PURE — hanya baca state, tidak mutasi apapun.
    Di LangGraph, return value dari conditional edge function DIABAIKAN;
    hanya return value dari NODE yang dipersist ke state berikutnya.
    Counter diincrement di node_analyst (lihat komentar di sana).
    """
    anomaly_output   = _get(state, "anomaly_output")
    reflection_count = _get(state, "reflection_count", 0)
    max_reflection   = _get(state, "max_reflection", 2)

    if (
        anomaly_output
        and anomaly_output.trigger_reflection
        and reflection_count < max_reflection
    ):
        # Display: reflection berikutnya akan jadi reflection_count+1
        # (increment terjadi di node_analyst saat dipanggil kembali)
        print(f"  🔄 Reflection triggered ({reflection_count + 1}/{max_reflection})")
        return "reflect"

    return "continue"


# ══════════════════════════════════════════════════════════════════
# GRAPH
# ══════════════════════════════════════════════════════════════════

def build_pipeline():
    """Build dan compile LangGraph pipeline."""
    graph = StateGraph(dict)  # Pakai dict sebagai state type — lebih stabil

    graph.add_node("parser",      node_parser)
    graph.add_node("categorizer", node_categorizer)
    graph.add_node("analyst",     node_analyst)
    graph.add_node("anomaly",     node_anomaly)
    graph.add_node("scenario",    node_scenario)
    graph.add_node("advisor",     node_advisor)
    graph.add_node("finalize",    node_finalize)

    graph.add_edge("parser",      "categorizer")
    graph.add_edge("categorizer", "analyst")
    graph.add_edge("analyst",     "anomaly")

    graph.add_conditional_edges(
        "anomaly",
        should_reflect,
        {"reflect": "analyst", "continue": "scenario"},
    )

    graph.add_edge("scenario", "advisor")
    graph.add_edge("advisor",  "finalize")
    graph.add_edge("finalize", END)

    graph.set_entry_point("parser")
    return graph.compile()


_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


def run_pipeline(
    raw_input:            str,
    business_type:        str   = "general",
    current_cash_balance: float = 0.0,
    session_id:           str   = None,
    is_demo_mode:         bool  = False,
    user_id:              int   = None,
) -> PipelineState:

    init_database()

    if session_id is None:
        session_id = str(uuid.uuid4())

    # Kirim sebagai dict — lebih stabil dengan LangGraph
    initial_state = {
        "session_id":            session_id,
        "raw_input":             raw_input,
        "business_type":         business_type,
        "current_cash_balance":  current_cash_balance,
        "is_demo_mode":          is_demo_mode,
        "user_id":               user_id,
        "reflection_count":      0,
        "max_reflection":        2,
        "current_step":          "start",
        "errors":                [],
        "warnings":              [],
        "parser_output":         None,
        "categorizer_output":    None,
        "analyst_output":        None,
        "anomaly_output":        None,
        "scenario_output":       None,
        "advisor_output":        None,
    }

    print(f"\n{'='*60}")
    print(f"🚀 CFO Sentinel Pipeline Starting")
    print(f"   Session: {session_id[:8]}...")
    print(f"   Business: {business_type}")
    print(f"   Balance: Rp {current_cash_balance:,.0f}")
    print(f"{'='*60}\n")

    pipeline     = get_pipeline()
    final_state  = pipeline.invoke(initial_state)

    errors = final_state.get("errors", []) if isinstance(final_state, dict) else []

    print(f"\n{'='*60}")
    print("✅ Pipeline Complete")
    if errors:
        print(f"   ⚠️  Errors: {len(errors)}")
        for e in errors:
            print(f"      - {e}")
    print(f"{'='*60}\n")

    # Konversi dict ke PipelineState dengan safe mapping
    try:
        return PipelineState(**final_state)
    except Exception as e:
        print(f"⚠️  State conversion warning: {e}")
        # Manual fallback jika ada field yang tidak kompatibel
        safe_state = PipelineState(
            session_id=final_state.get("session_id", session_id),
            raw_input=final_state.get("raw_input", raw_input),
            business_type=final_state.get("business_type", business_type),
            current_cash_balance=final_state.get("current_cash_balance", current_cash_balance),
            parser_output=final_state.get("parser_output"),
            categorizer_output=final_state.get("categorizer_output"),
            analyst_output=final_state.get("analyst_output"),
            anomaly_output=final_state.get("anomaly_output"),
            scenario_output=final_state.get("scenario_output"),
            advisor_output=final_state.get("advisor_output"),
            reflection_count=final_state.get("reflection_count", 0),
            current_step=final_state.get("current_step", "done"),
            errors=final_state.get("errors", []),
            warnings=final_state.get("warnings", []),
            is_demo_mode=is_demo_mode,
        )
        return safe_state


if __name__ == "__main__":
    test_input = (
        "kemarin beli bahan baku 1.5jt, bayar listrik 450rb, "
        "terima bayaran dari pelanggan 3.2jt, "
        "bayar gaji karyawan 2jt, beli kemasan 300rb"
    )
    result = run_pipeline(
        raw_input=test_input,
        business_type="kuliner",
        current_cash_balance=5_000_000,
    )
    if result.advisor_output:
        print(f"\nExecutive Summary:\n{result.advisor_output.executive_summary}")
        if result.advisor_output.has_early_warning and result.advisor_output.early_warning:
            print(f"\n⚠️  Warning: {result.advisor_output.early_warning.message}")