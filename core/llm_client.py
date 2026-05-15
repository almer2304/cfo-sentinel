"""
core/llm_client.py
CFO Sentinel — LLM Client Wrapper

Satu titik terpusat untuk semua LLM calls.
Menggunakan Groq API via groq SDK.
Handles: retry logic, token counting, fallback,
temperature per agent, dan error handling.
"""

import os
import time
import json
from typing import Optional
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

# ── Konfigurasi per agent ──────────────────────────────────────────
AGENT_CONFIG = {
    "parser": {
        "model": os.getenv("MODEL_PARSER", "llama-3.3-70b-versatile"),
        "temperature": 0.1,
        "max_tokens": 2000,
    },
    "categorizer": {
        "model": os.getenv("MODEL_CATEGORIZER", "llama-3.3-70b-versatile"),
        "temperature": 0.1,
        "max_tokens": 2000,
    },
    "analyst": {
        "model": os.getenv("MODEL_ANALYST", "llama-3.3-70b-versatile"),
        "temperature": 0.1,
        "max_tokens": 1500,
    },
    "anomaly": {
        "model": os.getenv("MODEL_ANOMALY", "llama-3.3-70b-versatile"),
        "temperature": 0.2,
        "max_tokens": 1500,
    },
    "scenario": {
        "model": os.getenv("MODEL_SCENARIO", "llama-3.3-70b-versatile"),
        "temperature": 0.3,
        "max_tokens": 2000,
    },
    "advisor": {
        "model": os.getenv("MODEL_ADVISOR", "llama-3.3-70b-versatile"),
        "temperature": 0.3,
        "max_tokens": 2000,
    },
}

MAX_RETRIES = 3
RETRY_DELAY = 2  # detik

# ── Client state ──────────────────────────────────────────────────
_client = None


def _get_client(force_reload=False):
    """Get or create API Client with API key."""
    global _client

    if _client is not None and not force_reload:
        return _client

    load_dotenv(override=True)
    provider = os.getenv("LLM_PROVIDER", "sumopod")

    if provider == "groq":
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("API key tidak ditemukan. Set GROQ_API_KEY di .env")
        _client = Groq(api_key=api_key)
    else:
        from openai import OpenAI
        api_key = os.getenv("SUMOPOD_API_KEY", "")
        if not api_key:
            raise ValueError("API key tidak ditemukan. Set SUMOPOD_API_KEY di .env")
        _client = OpenAI(api_key=api_key, base_url="https://ai.sumopod.com/v1")

    return _client


def call_llm(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    response_format: str = "text",  # "text" atau "json"
    override_model: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Kirim request ke LLM (Groq) dengan retry otomatis.

    Returns:
        tuple: (response_text, metadata)
        metadata berisi: model, tokens_used, duration_ms, attempt
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
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Build request kwargs
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

            # Token usage
            if hasattr(response, "usage") and response.usage:
                metadata["tokens_used"] = (
                    getattr(response.usage, "total_tokens", 0) or 0
                )

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
                print(f"[{agent_name}] Switching to rule-based fallback...")
                metadata["used_fallback"] = True
                metadata["duration_ms"] = int((time.time() - start_time) * 1000)
                fallback = _get_fallback_response(agent_name, user_message)
                return fallback, metadata

    return "", metadata


def call_llm_json(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    override_model: Optional[str] = None,
) -> tuple[dict, dict]:
    """
    Wrapper khusus untuk request yang mengharapkan JSON response.
    Otomatis parse JSON dan handle error parsing.

    Returns:
        tuple: (parsed_dict, metadata)
    """
    raw, metadata = call_llm(
        agent_name=agent_name,
        system_prompt=system_prompt,
        user_message=user_message,
        response_format="json",
        override_model=override_model,
    )

    try:
        # Bersihkan markdown code block jika ada
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])

        parsed = json.loads(cleaned)
        return parsed, metadata

    except json.JSONDecodeError as e:
        print(f"[{agent_name}] JSON parse error: {e}")
        print(f"   Raw response: {raw[:200]}...")
        return {}, metadata


def _get_fallback_response(agent_name: str, user_message: str) -> str:
    """
    Rule-based fallback jika LLM call gagal total.
    Sistem tetap jalan, output lebih sederhana tapi tidak crash.
    """
    fallbacks = {
        "parser": json.dumps({
            "transactions": [],
            "has_ambiguity": True,
            "ambiguity_notes": [
                "LLM tidak tersedia. Masukkan transaksi dalam format: "
                "'YYYY-MM-DD | income/expense | jumlah | deskripsi'"
            ],
        }),
        "categorizer": json.dumps({
            "transactions": [],
            "categories_found": [],
            "recurring_count": 0,
            "note": "Kategorisasi tidak tersedia saat ini.",
        }),
        "analyst": json.dumps({
            "total_income": 0,
            "total_expense": 0,
            "net_cashflow": 0,
            "cash_balance": 0,
            "burn_rate_daily": 0,
            "burn_rate_monthly": 0,
            "gross_margin": 0,
            "runway_days": {"minimum": 0, "expected": 0, "maximum": 0, "assumption": "Fallback"},
            "revenue_consistency": "Unknown",
            "health_score": {
                "current": 50,
                "previous_month": 50,
                "industry_average": 50,
                "danger_threshold": 20,
                "status": "SAFE",
                "trend": "STABLE"
            },
            "narrative": "Analisis otomatis tidak tersedia. Sistem berjalan dalam mode terbatas.",
            "period_start": "2023-01-01",
            "period_end": "2023-01-31",
            "business_type": "general",
            "forecast_30d": []
        }),
        "anomaly": json.dumps({
            "anomalies": [],
            "analyst_output_valid": True,
            "trigger_reflection": False,
            "overall_risk_level": "LOW",
            "note": "Deteksi anomali menggunakan rule-based fallback.",
        }),
        "scenario": json.dumps({
            "scenario_type": "custom",
            "parameter_name": "revenue",
            "parameter_change_pct": -20,
            "new_runway": {"minimum": 0, "expected": 0, "maximum": 0, "assumption": "Fallback"},
            "new_health_score": 50,
            "cuttable_costs": [],
            "fixed_costs": [],
            "total_cuttable_amount": 0,
            "chain_of_consequences": "Simulasi tidak tersedia saat ini.",
            "mitigation_steps": "Hubungi advisor secara langsung.",
            "mitigation_impact": "",
        }),
        "advisor": json.dumps({
            "has_early_warning": False,
            "early_warning": None,
            "action_items": [],
            "executive_summary": "Rekomendasi otomatis tidak tersedia saat ini.",
            "detailed_advice": "",
            "uncertainty_statement": "Sistem dalam mode fallback.",
        }),
    }
    return fallbacks.get(agent_name, "Layanan tidak tersedia saat ini.")


def estimate_cost(agent_name: str, input_text: str) -> dict:
    """
    Estimasi kasar token dan biaya sebelum call.
    1 token ≈ 4 karakter untuk teks Indonesia.
    Groq pricing: sangat murah / gratis untuk development.
    """
    estimated_input_tokens = len(input_text) // 4
    config = AGENT_CONFIG.get(agent_name, {})
    estimated_output_tokens = config.get("max_tokens", 1000) // 2

    total_tokens = estimated_input_tokens + estimated_output_tokens

    # Groq pricing (per 1M tokens) — Llama 3.3 70B
    # Input: $0.59/1M, Output: $0.79/1M
    cost_usd = (estimated_input_tokens * 0.00000059) + \
               (estimated_output_tokens * 0.00000079)
    cost_idr = cost_usd * 16000

    return {
        "estimated_tokens": total_tokens,
        "estimated_cost_usd": round(cost_usd, 6),
        "estimated_cost_idr": round(cost_idr, 2),
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("Testing LLM client configuration...")
    print(f"\nAgent configs:")
    for agent, config in AGENT_CONFIG.items():
        print(f"  {agent:12} -> model: {config['model']:<35} temp: {config['temperature']}")

    print(f"\nGroq API Key:")
    load_dotenv(override=True)
    key = os.getenv("GROQ_API_KEY", "")
    if key:
        print(f"  Key: {key[:10]}...{key[-4:]}")
    else:
        print("  [WARN] GROQ_API_KEY not found in .env")

    print("\nEstimated cost per session:")
    sample = "beli bahan baku 500rb, dapet bayaran dari pelanggan 2jt"
    total_idr = 0
    for agent in AGENT_CONFIG:
        est = estimate_cost(agent, sample)
        total_idr += est["estimated_cost_idr"]
        print(f"  {agent:12} -> ~{est['estimated_tokens']:,} tokens "
              f"= Rp {est['estimated_cost_idr']:,.0f}")
    print(f"\n  Total per sesi = Rp {total_idr:,.0f}")