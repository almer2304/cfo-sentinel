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
# max_tokens dioptimalkan sekecil mungkin agar response super cepat (di bawah 3 detik)
# dan mencegah token terbuang percuma.
AGENT_CONFIG = {
    "parser": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen3.6-flash"),
        "temperature": 0.1,
        "max_tokens": 1024,   # parser hanya return JSON transaksi pendek
    },
    "categorizer": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen3.6-flash"),
        "temperature": 0.1,
        "max_tokens": 1024,   # categorizer hanya return JSON klasifikasi
    },
    "analyst": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen3.6-flash"),  # flash untuk kecepatan menulis narasi pendek
        "temperature": 0.1,
        "max_tokens": 512,    # narasi dibatasi maksimal 3 kalimat
    },
    "anomaly": {
        "model": os.getenv("MODEL_ANOMALY", "qwen3.6-flash"),
        "temperature": 0.1,
        "max_tokens": 1024,   # JSON deteksi anomali ringkas
    },
    "scenario": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen3.6-flash"),  # flash untuk simulasi cepat
        "temperature": 0.2,
        "max_tokens": 1536,   # JSON simulasi skenario
    },
    "advisor": {
        "model": os.getenv("MODEL_ADVISORY", "qwen3.6-plus"),     # plus untuk kualitas saran strategis
        "temperature": 0.3,
        "max_tokens": 2048,   # JSON rekomendasi strategi
    },
    "classifier": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen3.6-flash"),
        "temperature": 0.1,
        "max_tokens": 1024,
    },
    "bookkeeper": {
        "model": os.getenv("MODEL_CLASSIFIER", "qwen3.6-flash"),
        "temperature": 0.1,
        "max_tokens": 1024,
    },
    "health": {
        "model": os.getenv("MODEL_HEALTH", "qwen3.6-plus"),
        "temperature": 0.1,
        "max_tokens": 512,
    },
    "report": {
        "model": os.getenv("MODEL_REPORT", "qwen3.6-plus"),
        "temperature": 0.2,
        "max_tokens": 1536,
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
    config = AGENT_CONFIG.get(agent_name, AGENT_CONFIG["advisor"])
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

    # Extra configs for models
    if "qwen3" in model_name.lower() or "qwen/qwen3" in model_name.lower():
        request_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        metadata["attempt"] = attempt
        try:
            response = client.chat.completions.create(**request_kwargs)
            content = response.choices[0].message.content or ""

            if hasattr(response, "usage") and response.usage:
                metadata["tokens_used"] = getattr(response.usage, "total_tokens", 0) or 0

            metadata["duration_ms"] = int((time.time() - start_time) * 1000)
            return content, metadata

        except Exception as e:
            last_error = e
            error_msg = str(e)
            print(f"[LLM-ERROR] [{agent_name}] Attempt {attempt}/{MAX_RETRIES} failed: {error_msg}")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    # Semua retry habis — raise error supaya pipeline terlihat gagal di log
    metadata["duration_ms"] = int((time.time() - start_time) * 1000)
    raise RuntimeError(
        f"[{agent_name}] LLM gagal setelah {MAX_RETRIES} percobaan. "
        f"Error terakhir: {last_error}"
    )


def call_llm_json(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    override_model: Optional[str] = None,
) -> tuple[dict, dict]:
    """Wrapper untuk request yang expect JSON response."""
    # Aggressive JSON-only enforcement in system prompt
    json_constraint = "\n\nCRITICAL: You must output ONLY a valid JSON object. No preamble, no explanation, no conversational text. Start your response with '{' and end with '}'."
    if json_constraint not in system_prompt:
        system_prompt += json_constraint

    raw, metadata = call_llm(
        agent_name=agent_name,
        system_prompt=system_prompt,
        user_message=user_message,
        response_format="json",
        override_model=override_model,
    )

    try:
        # ── Aggressive Cleaning ───────────────────────────────────────────
        import re
        content = raw.strip()
        
        # Remove thinking blocks
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        # Extract the JSON block using a more robust regex that handles nested structures
        start_idx = content.find('{')
        end_idx = content.rfind('}' )
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = content[start_idx:end_idx+1]
        else:
            json_str = content

        # Strip markdown fences
        if json_str.startswith("```"):
            json_str = re.sub(r'^```(?:json)?\n', '', json_str)
            json_str = re.sub(r'\n```$', '', json_str)
        
        parsed = json.loads(json_str)
        return parsed, metadata

    except (json.JSONDecodeError, AttributeError, Exception) as e:
        # Last ditch attempt: regex for anything between { and }
        try:
            import re
            match = re.search(r'(\{.*\})', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
                return parsed, metadata
        except:
            pass
            
        print(f"[{agent_name}] JSON parse error: {e}")
        print(f"[{agent_name}] Raw response (first 300 chars): {raw[:300]}")
        return {}, metadata


def _get_fallback_response(agent_name: str) -> str:
    """Rule-based fallback jika LLM call gagal total."""
    fallbacks = {
        "parser": json.dumps({
            "transactions": [],
            "has_ambiguity": False,
            "ambiguity_notes": ["Parsing otomatis tidak tersedia."]
        }),
        "categorizer": json.dumps({
            "transactions": [],
            "categories_found": [],
            "recurring_count": 0
        }),
        "classifier": json.dumps({
            "accounting_category": "Beban Lain",
            "sub_category": "Tidak Terklasifikasi",
            "is_recurring": False,
            "is_cogs": False,
            "is_asset_purchase": False,
            "confidence": 0.3,
            "sak_etap_note": "Klasifikasi fallback — perlu review manual.",
        }),
        "analyst": "Analisis otomatis tidak tersedia saat ini. Silakan coba lagi.",
        "health": "Analisis kesehatan keuangan tidak tersedia saat ini.",
        "anomaly": json.dumps({
            "anomalies": [],
            "overall_risk_level": "LOW",
            "analyst_output_valid": True,
            "trigger_reflection": False,
        }),
        "scenario": json.dumps({
            "scenario_type": "unavailable",
            "new_runway": {"minimum": 0, "expected": 0, "maximum": 0, "assumption": ""},
            "new_health_score": 0,
            "cuttable_costs": [],
            "fixed_costs": [],
            "total_cuttable_amount": 0,
        }),
        "advisor": json.dumps({
            "has_early_warning": False,
            "action_items": [],
            "executive_summary": "Saran strategis tidak tersedia saat ini.",
            "detailed_advice": "",
            "uncertainty_statement": "",
            "conflict_detected": False,
        }),
        "report": json.dumps({
            "period": "",
            "summary": "Laporan tidak tersedia saat ini.",
            "highlights": [],
        }),
    }
    return fallbacks.get(agent_name, "Layanan tidak tersedia saat ini.")