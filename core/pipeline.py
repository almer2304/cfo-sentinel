"""
core/pipeline.py
Background Pipeline Orchestrator
Dijalankan di thread terpisah setelah setiap transaksi disimpan.
Urutan: Classifier (Agent 1) → Health (Agent 2) → Anomaly (Agent 3)
"""

import threading
import traceback
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def _run_pipeline(transaction: dict, user_id: int):
    """
    Eksekusi pipeline 3 agent secara sequential.
    Dipanggil di background thread — JANGAN await, JANGAN block.
    """
    tx_code = transaction.get("transaction_code", "?")
    today = datetime.now(WIB).strftime('%Y-%m-%d')

    try:
        # ── Agent 1: Classifier ─────────────────────────────────────────
        try:
            from agents.classifier_agent import run_classifier_agent
            result_cls = run_classifier_agent(transaction, user_id)
            print(f"[PIPELINE] Agent 1 Classifier OK → {result_cls.get('accounting_type')} [{tx_code}]")
        except Exception as e:
            print(f"[PIPELINE] Agent 1 ERROR: {e}")

        # ── Agent 2: Health ─────────────────────────────────────────────
        try:
            from agents.health_agent import run_health_agent
            result_health = run_health_agent(user_id)
            print(
                f"[PIPELINE] Agent 2 Health OK → "
                f"score={result_health.get('health_score')}, "
                f"runway={result_health.get('runway_days')}d [user={user_id}]"
            )
        except Exception as e:
            print(f"[PIPELINE] Agent 2 ERROR: {e}")

        # ── Agent 3: Anomaly ────────────────────────────────────────────
        try:
            from agents.anomaly_agent_new import run_anomaly_agent
            result_anom = run_anomaly_agent(user_id)
            n_anomalies = len(result_anom.get("anomalies", []))
            print(
                f"[PIPELINE] Agent 3 Anomaly OK → "
                f"{n_anomalies} anomali, risk={result_anom.get('overall_risk')} [user={user_id}]"
            )
        except Exception as e:
            print(f"[PIPELINE] Agent 3 ERROR: {e}")

        print(f"[PIPELINE] ✓ Pipeline selesai untuk user={user_id}, tx={tx_code}, date={today}")

    except Exception as e:
        print(f"[PIPELINE] FATAL ERROR: {e}")
        traceback.print_exc()


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
