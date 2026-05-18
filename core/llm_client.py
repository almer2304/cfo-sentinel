"""
core/llm_client.py
CFO Sentinel — LLM Client Wrapper

Satu titik terpusat untuk semua LLM calls.
Model: qwen/qwen3-6b-plus via Sumopod AI (OpenAI-compatible API).
"""

import os
import time
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── Konfigurasi per agent ──────────────────────────────────────────
AGENT_CONFIG = {
    "classifier": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen/qwen3-6b-plus"),
        "temperature": 0.1,   # deterministic — klasifikasi akuntansi
        "max_tokens": 2000,
    },
    "health": {
        "model": os.getenv("MODEL_HEALTH", "qwen/qwen3-6b-plus"),
        "temperature": 0.1,   # deterministic — kalkulasi metrik
        "max_tokens": 2000,
    },
    "anomaly": {
        "model": os.getenv("MODEL_ANOMALY", "qwen/qwen3-6b-plus"),
        "temperature": 0.2,   # sedikit kreatif untuk deteksi pola
        "max_tokens": 2000,
    },
    "advisory": {
        "model": os.getenv("MODEL_ADVISORY", "qwen/qwen3-6b-plus"),
        "temperature": 0.3,   # lebih ekspresif untuk chat
        "max_tokens": 1500,
    },
    "report": {
        "model": os.getenv("MODEL_REPORT", "qwen/qwen3-6b-plus"),
        "temperature": 0.2,   # ringkasan terstruktur
        "max_tokens": 2000,
    },
}

MAX_RETRIES = 3
RETRY_DELAY = 2

_client = None


def _get_client(force_reload=False):
    """Get atau buat OpenAI-compatible client untuk Sumopod."""
    global _client
    if _client is not None and not force_reload:
        return _client

    load_dotenv(override=True)
    from openai import OpenAI

    api_key = os.getenv("SUMOPOD_API_KEY", "")
    if not api_key:
        raise ValueError("SUMOPOD_API_KEY tidak ditemukan di .env")

    _client = OpenAI(
        api_key=api_key,
        base_url="https://ai.sumopod.com/v1",
    )
    return _client


def call_llm(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    response_format: str = "text",   # "text" atau "json"
    override_model: Optional[str] = None,
    conversation_history: list = None,  # untuk chat multi-turn
) -> tuple[str, dict]:
    """
    Kirim request ke LLM dengan retry otomatis.
    Returns: (response_text, metadata)
    """
    client = _get_client()
    config = AGENT_CONFIG.get(agent_name, AGENT_CONFIG["advisory"])
    model_name = override_model or config["model"]

    metadata = {
        "agent": agent_name,
        "model": model_name,
        "tokens_used": 0,
        "duration_ms": 0,
        "attempt": 1,
        "used_fallback": False,
    }

    start_time = time.time()

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    request_kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
    }

    if response_format == "json":
        request_kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(1, MAX_RETRIES + 1):
        metadata["attempt"] = attempt
        try:
            client = _get_client()
            response = client.chat.completions.create(**request_kwargs)
            content = response.choices[0].message.content or ""

            if hasattr(response, "usage") and response.usage:
                metadata["tokens_used"] = getattr(response.usage, "total_tokens", 0) or 0

            metadata["duration_ms"] = int((time.time() - start_time) * 1000)
            return content, metadata

        except Exception as e:
            error_msg = str(e)
            is_rate_limit = "429" in error_msg or "rate" in error_msg.lower()
            print(f"[{agent_name}] Attempt {attempt}/{MAX_RETRIES} failed: "
                  f"{'RATE LIMITED' if is_rate_limit else error_msg[:100]}")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                print(f"[{agent_name}] Switching to fallback...")
                metadata["used_fallback"] = True
                metadata["duration_ms"] = int((time.time() - start_time) * 1000)
                return _get_fallback_response(agent_name), metadata

    return "", metadata


def call_llm_json(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    override_model: Optional[str] = None,
) -> tuple[dict, dict]:
    """Wrapper untuk request yang expect JSON response."""
    raw, metadata = call_llm(
        agent_name=agent_name,
        system_prompt=system_prompt,
        user_message=user_message,
        response_format="json",
        override_model=override_model,
    )

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        parsed = json.loads(cleaned)
        return parsed, metadata

    except json.JSONDecodeError as e:
        # Auto-repair truncated JSON
        try:
            fixed = cleaned
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')
            if open_brackets > 0:
                fixed += ']' * open_brackets
            if open_braces > 0:
                fixed += '}' * open_braces
            parsed = json.loads(fixed)
            print(f"[{agent_name}] JSON auto-repaired!")
            return parsed, metadata
        except json.JSONDecodeError:
            print(f"[{agent_name}] JSON parse error: {e}")
            return {}, metadata


def _get_fallback_response(agent_name: str) -> str:
    """Rule-based fallback jika LLM call gagal total."""
    fallbacks = {
        "classifier": json.dumps({
            "accounting_category": "Beban Lain",
            "sub_category": "Tidak Terklasifikasi",
            "is_recurring": False,
            "is_cogs": False,
            "is_asset_purchase": False,
            "confidence": 0.3,
            "sak_etap_note": "Klasifikasi fallback — perlu review manual.",
        }),
        "health": "Analisis otomatis tidak tersedia saat ini. Sistem berjalan dalam mode terbatas.",
        "anomaly": json.dumps({
            "anomalies": [],
            "overall_risk_level": "LOW",
            "has_critical": False,
            "summary": "Deteksi anomali tidak tersedia saat ini.",
        }),
        "advisory": "Maaf, saya sedang tidak bisa menjawab. Coba lagi dalam beberapa saat.",
        "report": json.dumps({
            "period": "",
            "summary": "Laporan tidak tersedia saat ini.",
            "highlights": [],
        }),
    }
    return fallbacks.get(agent_name, "Layanan tidak tersedia saat ini.")