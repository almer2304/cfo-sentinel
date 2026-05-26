"""
core/pipeline.py
Background Pipeline Orchestrator
Dijalankan di thread terpisah setelah setiap transaksi disimpan.
Urutan: Classifier (Agent 1) → Health (Agent 2) → Anomaly (Agent 3) → Scenario (Agent 4) → Advisor (Agent 5) → Report (Agent 6)
"""

import threading
import time as _time
import json
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def _run_pipeline(transaction: dict, user_id: int):
    """
    Worker function: menjalankan agent secara sequential.
    """
    now = datetime.now(WIB)
    today = now.strftime('%Y-%m-%d')
    month_start = now.strftime('%Y-%m-01')

    print(f"[PIPELINE] Starting for user {user_id}, transaction {transaction.get('transaction_code')}")

    # ── Agent 1: Bookkeeper (Deterministic Rules + LLM) ──────────
    t0 = _time.time()
    category = "Pending"
    acc_type = "other"
    try:
        from core.llm_client import call_llm_json
        from core.prompts import get_categorizer_prompt
        from agents.bookkeeper_agent import run_bookkeeper_agent, _update_first_transaction, _insert_split_transaction
        from core.database import get_connection

        # Coba pakai LLM dulu untuk klasifikasi yang lebih cerdas
        tx_list = []
        try:
            prompt = get_categorizer_prompt()
            parsed_json, _ = call_llm_json(
                agent_name="bookkeeper",
                system_prompt=prompt,
                user_message=f"Klasifikasikan transaksi ini: {transaction.get('raw_input')}",
            )
            tx_list = parsed_json.get("transactions", [])
        except Exception as e:
            print(f"[PIPELINE] LLM Bookkeeper fallback: {e}")

        if tx_list:
            conn = get_connection()
            cursor = conn.cursor()
            try:
                _update_first_transaction(cursor, transaction, tx_list[0], user_id)
                for extra in tx_list[1:]:
                    _insert_split_transaction(cursor, transaction, extra, user_id)
                conn.commit()
                category = tx_list[0].get("category")
                acc_type = tx_list[0].get("accounting_type")
            finally:
                conn.close()
        else:
            # Deterministic Fallback
            result_book = run_bookkeeper_agent(transaction, user_id)
            category = result_book.get("category")
            acc_type = result_book.get("accounting_type")

        print(
            f"[PIPELINE] Agent 1 Bookkeeper OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ {category} ({acc_type}) [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 1 Bookkeeper ERROR: {e}")

    # ── Agent 2: Health ─────────────────────────────────────────────
    t0 = _time.time()
    health_score = 0
    runway = 0
    burn_day = 0
    cash_balance = 0
    income_month = 0
    expense_month = 0
    try:
        from agents.health_agent import run_health_agent
        from core.database_new import get_financial_summary
        
        result_health = run_health_agent(user_id)
        health_score = result_health.get("health_score", 0)
        runway = result_health.get("runway_days", 0)
        burn_day = result_health.get("burn_rate_daily", 0)
        cash_balance = result_health.get("cash_balance", 0)
        
        financial = get_financial_summary(user_id, month_start, today)
        income_month = financial.get("total_income", 0) or 0
        expense_month = financial.get("total_expense", 0) or 0
        
        print(
            f"[PIPELINE] Agent 2 Health OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ score={health_score} [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 2 Health ERROR: {e}")

    # ── Agent 3: Anomaly ────────────────────────────────────────────
    t0 = _time.time()
    result_anom = {}
    try:
        from agents.anomaly_agent_new import run_anomaly_agent
        result_anom = run_anomaly_agent(user_id)
        n_anomalies = len(result_anom.get("anomalies", []))
        print(
            f"[PIPELINE] Agent 3 Anomaly OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ {n_anomalies} anomali, risk={result_anom.get('overall_risk')} [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 3 Anomaly ERROR: {e}")

    # ── Agent 4: Scenario ───────────────────────────────────────────
    t0 = _time.time()
    result_scenario = None
    try:
        from agents.scenario_agent import run_scenario_agent
        
        # Mock objects untuk scenario agent (v1 compatibility)
        analyst_mock = type('obj', (object,), {
            "session_id": f"scenario-{user_id}-{today}",
            "cash_balance": cash_balance,
            "burn_rate_daily": burn_day,
            "total_income": income_month,
            "total_expense": expense_month,
            "health_score": type('obj', (object,), {"current": health_score}),
            "runway_days": type('obj', (object,), {"expected": runway}),
            "journal_revenue": income_month,
            "burn_rate_monthly": expense_month
        })
        
        from core.database_new import get_spending_by_category_efficient
        spending = get_spending_by_category_efficient(user_id, month_start, today)
        categorizer_mock = type('obj', (object,), {
            "categories_found": [s["category"] for s in spending],
            "transactions": [{"category": s["category"], "amount": s["total"], "type": "expense"} for s in spending]
        })
        
        result_scenario = run_scenario_agent(
            analyst_output=analyst_mock,
            categorizer_output=categorizer_mock,
            scenario_description="Jika penjualan turun 20%",
            parameter_name="revenue",
            parameter_change_pct=-20.0
        )
        
        # Simpan ke DB
        from core.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        try:
            scenario_data = {
                "scenario_type": result_scenario.scenario_type,
                "new_runway_expected": result_scenario.new_runway.expected,
                "new_health_score": result_scenario.new_health_score,
                "chain_of_consequences": result_scenario.chain_of_consequences,
                "mitigation_steps": result_scenario.mitigation_steps,
                "total_cuttable_amount": result_scenario.total_cuttable_amount
            }
            cursor.execute("""
                UPDATE daily_summaries
                SET scenario_json = ?
                WHERE user_id = ? AND date_only = ?
            """, (json.dumps(scenario_data), user_id, today))
            conn.commit()
        finally:
            conn.close()
            
        print(
            f"[PIPELINE] Agent 4 Scenario OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ new_health={result_scenario.new_health_score} [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 4 Scenario ERROR: {e}")

    # ── Agent 5: Advisor & Strategic Actions ────────────────────────
    t0 = _time.time()
    try:
        from agents.advisor_agent import run_advisor_agent
        from core.schemas import AnalystOutput, AnomalyOutput, ConfidenceRange, HealthScoreData, AnomalyData
        
        analyst_mock_adv = AnalystOutput(
            session_id=f"advisor-{user_id}-{today}",
            period_start=month_start,
            period_end=today,
            total_income=income_month,
            total_expense=expense_month,
            net_cashflow=income_month - expense_month,
            cash_balance=cash_balance,
            burn_rate_daily=burn_day,
            burn_rate_monthly=expense_month,
            net_margin=( (income_month - expense_month) / income_month * 100 ) if income_month > 0 else 0,
            runway_days=ConfidenceRange(minimum=max(0, runway*0.8), expected=runway, maximum=runway*1.2),
            health_score=HealthScoreData(current=health_score),
            business_type="general",
            narrative="",
            forecast_30d=[],
            revenue_consistency=0
        )
        
        anom_list = result_anom.get("anomalies", [])
        anomaly_mock_adv = AnomalyOutput(
            session_id=analyst_mock_adv.session_id,
            anomalies=[AnomalyData(**a) for a in anom_list],
            overall_risk_level=result_anom.get("overall_risk", "LOW")
        )
        
        advisor_res = run_advisor_agent(analyst_mock_adv, anomaly_mock_adv, result_scenario)
        
        from core.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        try:
            actions_list = [
                {
                    "title": item.title,
                    "description": item.description,
                    "urgency": item.urgency,
                    "expected_impact": item.estimated_impact
                }
                for item in advisor_res.action_items
            ]
            cursor.execute("""
                UPDATE daily_summaries
                SET actions_json = ?
                WHERE user_id = ? AND date_only = ?
            """, (json.dumps(actions_list), user_id, today))
            conn.commit()
        finally:
            conn.close()
            
        print(
            f"[PIPELINE] Agent 5 Advisor OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ {len(advisor_res.action_items)} actions [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 5 Advisor ERROR: {e}")

    # ── Agent 6: Report ─────────────────────────────────────────────
    t0 = _time.time()
    try:
        from agents.report_agent import run_report_agent
        run_report_agent(user_id, today)
        print(
            f"[PIPELINE] Agent 6 Report OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ summary updated [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 6 Report ERROR: {e}")

    print(f"[PIPELINE] All done for user {user_id} at {datetime.now(WIB)}")


def trigger_pipeline(transaction: dict, user_id: int):
    """
    Trigger pipeline di background thread.
    Return SEGERA — non-blocking.
    """
    t = threading.Thread(
        target=_run_pipeline,
        args=(transaction, user_id),
        daemon=True,
        name=f"pipeline-{transaction.get('transaction_code', 'unknown')}",
    )
    t.start()
    print(f"[PIPELINE] Background thread started: {t.name}")
