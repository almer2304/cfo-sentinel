"""
core/pipeline.py
Background Pipeline Orchestrator
Dijalankan di thread terpisah setelah setiap transaksi disimpan.
Urutan: Classifier (Agent 1) → Health (Agent 2) → Anomaly (Agent 3) → Report (Agent 5)
"""

import threading
import traceback
import time as _time
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def _run_pipeline(transaction: dict, user_id: int):
    """
    Eksekusi pipeline 4 agent secara sequential.
    Setiap agent punya try-except sendiri — error satu agent
    tidak menghentikan agent berikutnya.
    Dipanggil di background thread — JANGAN await, JANGAN block.
    """
    tx_code = transaction.get("transaction_code", "?")
    today = datetime.now(WIB).strftime('%Y-%m-%d')
    pipeline_start = _time.time()

    print(f"[PIPELINE] >>> Mulai pipeline untuk tx={tx_code}, user={user_id}")

    # ── Agent 1: Bookkeeper ─────────────────────────────────────────
    t0 = _time.time()
    try:
        from agents.bookkeeper_agent import run_bookkeeper_agent
        result_book = run_bookkeeper_agent(transaction, user_id)
        print(
            f"[PIPELINE] Agent 1 Bookkeeper OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ {result_book.get('accounting_type')} [{tx_code}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 1 Bookkeeper ERROR: {e}")

    # ── Agent 2: Health ─────────────────────────────────────────────
    t0 = _time.time()
    try:
        from agents.health_agent import run_health_agent
        result_health = run_health_agent(user_id)
        print(
            f"[PIPELINE] Agent 2 Health OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ score={result_health.get('health_score')} [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 2 Health ERROR: {e}")

    # ── Agent 3: Anomaly ────────────────────────────────────────────
    t0 = _time.time()
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

    # ── Agent 5: Report ─────────────────────────────────────────────
    t0 = _time.time()
    try:
        from agents.report_agent import run_report_agent
        narrative = run_report_agent(user_id, today)
        print(
            f"[PIPELINE] Agent 5 Report OK ({int((_time.time()-t0)*1000)}ms) "
            f"→ {narrative[:60]}... [user={user_id}]"
        )
    except Exception as e:
        print(f"[PIPELINE] Agent 5 Report ERROR: {e}")

    total_ms = int((_time.time() - pipeline_start) * 1000)
    print(f"[PIPELINE] ✓ Pipeline SELESAI — {total_ms}ms, user={user_id}, tx={tx_code}")


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
