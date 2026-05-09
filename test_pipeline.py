"""
test_pipeline.py
CFO Sentinel — Integration Test

Tes keseluruhan pipeline multi-agent dari Parser sampai Advisor.
Menjalankan pipeline sungguhan dengan Groq API (Llama 3.3 70B).
"""

import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

def test_imports():
    """Test 1: Pastikan semua import berjalan."""
    print("=" * 60)
    print("TEST 1: Import checks")
    print("=" * 60)
    
    errors = []
    
    try:
        from core.schemas import (
            PipelineState, ParserOutput, CategorizerOutput,
            AnalystOutput, AnomalyOutput, ScenarioOutput, AdvisorOutput,
            ConfidenceRange, HealthScore, ForecastPoint,
            ParsedTransaction, CategorizedTransaction,
        )
        print("  [OK] core.schemas")
    except Exception as e:
        errors.append(f"core.schemas: {e}")
        print(f"  [FAIL] core.schemas: {e}")
    
    try:
        from core.database import init_database, get_connection
        print("  [OK] core.database")
    except Exception as e:
        errors.append(f"core.database: {e}")
        print(f"  [FAIL] core.database: {e}")

    try:
        from core.llm_client import call_llm, call_llm_json, AGENT_CONFIG
        print("  [OK] core.llm_client")
    except Exception as e:
        errors.append(f"core.llm_client: {e}")
        print(f"  [FAIL] core.llm_client: {e}")

    try:
        from core.prompts import (
            get_parser_prompt, get_categorizer_prompt,
            ANALYST_SYSTEM, ANOMALY_SYSTEM, SCENARIO_SYSTEM, ADVISOR_SYSTEM,
        )
        print("  [OK] core.prompts")
    except Exception as e:
        errors.append(f"core.prompts: {e}")
        print(f"  [FAIL] core.prompts: {e}")

    try:
        from core.memory import (
            get_industry_health_avg, load_baselines_for_analysis,
            get_historical_context,
        )
        print("  [OK] core.memory")
    except Exception as e:
        errors.append(f"core.memory: {e}")
        print(f"  [FAIL] core.memory: {e}")

    try:
        from agents.parser_agent import run_parser_agent
        print("  [OK] agents.parser_agent")
    except Exception as e:
        errors.append(f"agents.parser_agent: {e}")
        print(f"  [FAIL] agents.parser_agent: {e}")

    try:
        from agents.categorizer_agent import run_categorizer_agent
        print("  [OK] agents.categorizer_agent")
    except Exception as e:
        errors.append(f"agents.categorizer_agent: {e}")
        print(f"  [FAIL] agents.categorizer_agent: {e}")

    try:
        from agents.analyst_agent import run_analyst_agent
        print("  [OK] agents.analyst_agent")
    except Exception as e:
        errors.append(f"agents.analyst_agent: {e}")
        print(f"  [FAIL] agents.analyst_agent: {e}")

    try:
        from agents.anomaly_agent import run_anomaly_agent
        print("  [OK] agents.anomaly_agent")
    except Exception as e:
        errors.append(f"agents.anomaly_agent: {e}")
        print(f"  [FAIL] agents.anomaly_agent: {e}")

    try:
        from agents.scenario_agent import run_scenario_agent
        print("  [OK] agents.scenario_agent")
    except Exception as e:
        errors.append(f"agents.scenario_agent: {e}")
        print(f"  [FAIL] agents.scenario_agent: {e}")

    try:
        from agents.advisor_agent import run_advisor_agent
        print("  [OK] agents.advisor_agent")
    except Exception as e:
        errors.append(f"agents.advisor_agent: {e}")
        print(f"  [FAIL] agents.advisor_agent: {e}")

    try:
        from core.orchestrator import build_pipeline, run_pipeline
        print("  [OK] core.orchestrator")
    except Exception as e:
        errors.append(f"core.orchestrator: {e}")
        print(f"  [FAIL] core.orchestrator: {e}")

    if errors:
        print(f"\n  IMPORT TEST FAILED: {len(errors)} errors")
        return False
    print(f"\n  All imports OK!")
    return True


def test_database():
    """Test 2: Database initialization."""
    print("\n" + "=" * 60)
    print("TEST 2: Database")
    print("=" * 60)
    
    from core.database import init_database, get_connection
    try:
        init_database()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        expected = ["transactions", "analytics", "anomalies", "recommendations",
                     "monthly_snapshots", "spending_baselines", "agent_logs", "scenarios"]
        missing = [t for t in expected if t not in tables]
        
        if missing:
            print(f"  [WARN] Missing tables: {missing}")
        else:
            print(f"  [OK] All {len(expected)} tables exist: {tables}")
        return True
    except Exception as e:
        print(f"  [FAIL] Database init error: {e}")
        return False


def test_schemas():
    """Test 3: Pydantic schema validation."""
    print("\n" + "=" * 60)
    print("TEST 3: Schema validation")
    print("=" * 60)
    
    from core.schemas import (
        ParsedTransaction, CategorizedTransaction,
        HealthScore, ConfidenceRange, ForecastPoint,
    )
    
    try:
        tx = ParsedTransaction(
            date="2026-05-07", amount=500000,
            type="expense", description="Beli bahan baku"
        )
        print(f"  [OK] ParsedTransaction: {tx.description}")
        
        cat_tx = CategorizedTransaction(
            date="2026-05-07", amount=500000,
            type="expense", description="Beli bahan baku",
            category="Bahan Baku", sub_category="Makanan",
        )
        print(f"  [OK] CategorizedTransaction: {cat_tx.category}/{cat_tx.sub_category}")

        # Test attribute access (NOT .get())
        assert cat_tx.category == "Bahan Baku"
        assert cat_tx.amount == 500000
        assert cat_tx.type == "expense"
        print(f"  [OK] Attribute access works correctly")
        
        hs = HealthScore(current=72, previous_month=68, industry_average=70,
                         danger_threshold=50, trend="UP")
        print(f"  [OK] HealthScore: {hs.current}/100 status={hs.status}")
        
        cr = ConfidenceRange(minimum=20, expected=30, maximum=40)
        print(f"  [OK] ConfidenceRange: {cr.minimum}-{cr.expected}-{cr.maximum}")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Schema error: {e}")
        return False


def test_memory():
    """Test 4: Memory layer (cold start + baselines)."""
    print("\n" + "=" * 60)
    print("TEST 4: Memory layer")
    print("=" * 60)
    
    from core.database import init_database
    from core.memory import (
        get_industry_health_avg, load_baselines_for_analysis,
        get_historical_context,
    )
    init_database()
    
    try:
        avg = get_industry_health_avg("kuliner")
        print(f"  [OK] Industry avg (kuliner): {avg}/100")
        
        baselines = load_baselines_for_analysis("kuliner")
        print(f"  [OK] Baselines loaded: {len(baselines)} categories")
        for b in baselines[:3]:
            print(f"       {b['category']}: Rp {b['avg_monthly']:,.0f}/bulan")
        
        ctx = get_historical_context("kuliner")
        print(f"  [OK] Historical context: {ctx[:60]}...")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Memory error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_llm_connection():
    """Test 5: LLM API call (Groq)."""
    print("\n" + "=" * 60)
    print("TEST 5: LLM connection (Groq)")
    print("=" * 60)
    
    from core.llm_client import call_llm
    
    try:
        response, meta = call_llm(
            agent_name="parser",
            system_prompt="Kamu adalah asisten test. Jawab singkat.",
            user_message="Balas dengan: OK_TEST_123",
            response_format="text",
        )
        
        print(f"  Response: {response[:100]}")
        print(f"  Model: {meta['model']}")
        print(f"  Tokens: {meta['tokens_used']}")
        print(f"  Duration: {meta['duration_ms']}ms")
        print(f"  Fallback: {meta['used_fallback']}")
        
        if meta["used_fallback"]:
            print(f"  [WARN] Using fallback — API key may be invalid")
            return False
        
        print(f"  [OK] LLM connection working!")
        return True
    except Exception as e:
        print(f"  [FAIL] LLM error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_pipeline():
    """Test 6: Full pipeline end-to-end."""
    print("\n" + "=" * 60)
    print("TEST 6: Full pipeline (end-to-end)")
    print("=" * 60)
    
    from core.orchestrator import run_pipeline
    
    test_input = (
        "kemarin beli bahan baku 1.5jt, bayar listrik 450rb, "
        "terima bayaran dari pelanggan 3.2jt, "
        "bayar gaji karyawan 2jt, beli kemasan 300rb"
    )
    
    print(f"  Input: {test_input}")
    print(f"  Running pipeline...\n")
    
    try:
        result = run_pipeline(
            raw_input=test_input,
            business_type="kuliner",
            current_cash_balance=5_000_000,
        )
        
        print(f"\n  --- PIPELINE RESULTS ---")
        
        # Parser
        if result.parser_output:
            print(f"  [OK] Parser: {result.parser_output.total_parsed} transactions")
        else:
            print(f"  [FAIL] Parser: no output")
        
        # Categorizer
        if result.categorizer_output:
            print(f"  [OK] Categorizer: {result.categorizer_output.categories_found}")
            print(f"       Income:  Rp {result.categorizer_output.total_income:,.0f}")
            print(f"       Expense: Rp {result.categorizer_output.total_expense:,.0f}")
        else:
            print(f"  [FAIL] Categorizer: no output")
        
        # Analyst
        if result.analyst_output:
            hs = result.analyst_output.health_score
            print(f"  [OK] Analyst: Health={hs.current:.0f}/100 "
                  f"Runway={result.analyst_output.runway_days.expected:.0f}d")
        else:
            print(f"  [FAIL] Analyst: no output")
        
        # Anomaly
        if result.anomaly_output:
            print(f"  [OK] Anomaly: {result.anomaly_output.total_anomalies} found, "
                  f"Risk={result.anomaly_output.overall_risk_level}")
        else:
            print(f"  [FAIL] Anomaly: no output")
        
        # Scenario
        if result.scenario_output:
            print(f"  [OK] Scenario: Runway={result.scenario_output.new_runway.expected:.0f}d, "
                  f"Health={result.scenario_output.new_health_score:.0f}")
        else:
            print(f"  [WARN] Scenario: no output (may be expected if skipped)")
        
        # Advisor
        if result.advisor_output:
            print(f"  [OK] Advisor: {len(result.advisor_output.action_items)} actions")
            print(f"       Summary: {result.advisor_output.executive_summary[:100]}...")
            if result.advisor_output.has_early_warning:
                print(f"       Warning: {result.advisor_output.early_warning.message[:80]}...")
        else:
            print(f"  [FAIL] Advisor: no output")
        
        # Errors
        if result.errors:
            print(f"\n  [WARN] Pipeline errors:")
            for err in result.errors:
                print(f"    - {err}")
        
        # Overall verdict
        all_agents = [
            result.parser_output, result.categorizer_output,
            result.analyst_output, result.anomaly_output,
            result.advisor_output,
        ]
        success_count = sum(1 for a in all_agents if a is not None)
        total = len(all_agents)
        
        print(f"\n  PIPELINE SCORE: {success_count}/{total} agents produced output")
        return success_count >= 4  # At least 4 of 5 core agents must work
        
    except Exception as e:
        print(f"  [FAIL] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "#" * 60)
    print("#   CFO SENTINEL — INTEGRATION TEST SUITE")
    print("#" * 60)
    
    results = {}
    
    # Test 1: Imports
    results["imports"] = test_imports()
    if not results["imports"]:
        print("\nCRITICAL: Import errors. Cannot continue.")
        return
    
    # Test 2: Database
    results["database"] = test_database()
    
    # Test 3: Schemas
    results["schemas"] = test_schemas()
    
    # Test 4: Memory
    results["memory"] = test_memory()
    
    # Test 5: LLM
    results["llm"] = test_llm_connection()
    
    # Test 6: Full pipeline (only if LLM works)
    if results["llm"]:
        results["pipeline"] = test_full_pipeline()
    else:
        print("\nSkipping full pipeline test — LLM connection failed.")
        results["pipeline"] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        icon = "[OK]" if passed else "[!!]"
        print(f"  {icon} {name:15} {status}")
    
    total_pass = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  Result: {total_pass}/{total} tests passed")
    
    if total_pass == total:
        print("  STATUS: ALL SYSTEMS GO!")
    elif total_pass >= total - 1:
        print("  STATUS: Minor issues, mostly functional")
    else:
        print("  STATUS: Needs attention")


if __name__ == "__main__":
    main()
