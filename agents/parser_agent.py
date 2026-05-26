"""
agents/parser_agent.py
CFO Sentinel - Parser Agent

Parser boleh memakai LLM, tetapi fallback deterministik wajib tersedia agar
endpoint analisis tidak mati saat API key/model bermasalah.
"""

from core.finance_rules import classify_raw_transactions, infer_transaction_date
from core.llm_client import call_llm_json
from core.prompts import get_parser_prompt
from core.schemas import ParserOutput


def _fallback_parse(session_id: str, raw_input: str, reason: str = "") -> ParserOutput:
    result = classify_raw_transactions(raw_input)
    transactions = []

    for tx in result.get("transactions", []):
        transactions.append({
            "date": tx.get("date") or infer_transaction_date(raw_input),
            "amount": tx.get("amount", 0),
            "type": tx.get("type", "expense"),
            "description": tx.get("description", raw_input),
            "accounting_type": tx.get("accounting_type"),
            "debit_account": tx.get("debit_account"),
            "credit_account": tx.get("credit_account"),
            "category": tx.get("category"),
            "sub_category": tx.get("sub_category"),
            "is_pnl": tx.get("is_pnl"),
            "is_business": tx.get("is_business", True),
            "confidence": tx.get("confidence", 0.6),
            "needs_clarification": False,
            "clarification_question": None,
        })

    notes = []
    if reason:
        notes.append(f"Parser fallback aktif: {reason}")
    if result.get("reasoning"):
        notes.append(result["reasoning"])

    return ParserOutput(
        session_id=session_id,
        raw_input=raw_input,
        transactions=transactions,
        total_parsed=len(transactions),
        has_ambiguity=not transactions,
        ambiguity_notes=notes or ["Tidak ada nominal yang bisa diparse."],
    )


def run_parser_agent(session_id: str, raw_input: str) -> ParserOutput:
    """
    Menjalankan Parser Agent untuk mengubah input teks menjadi JSON terstruktur.
    """
    system_prompt = get_parser_prompt()

    try:
        parsed_json, _ = call_llm_json(
            agent_name="parser",
            system_prompt=system_prompt,
            user_message=raw_input,
        )
        transactions = parsed_json.get("transactions", [])
        if not transactions:
            return _fallback_parse(session_id, raw_input, "LLM tidak mengembalikan transaksi.")

        return ParserOutput(
            session_id=session_id,
            raw_input=raw_input,
            transactions=transactions,
            total_parsed=len(transactions),
            has_ambiguity=parsed_json.get("has_ambiguity", False),
            ambiguity_notes=parsed_json.get("ambiguity_notes", []),
        )
    except Exception as exc:
        return _fallback_parse(session_id, raw_input, str(exc))
