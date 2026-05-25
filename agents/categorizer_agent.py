"""
agents/categorizer_agent.py
CFO Sentinel - Categorizer Agent

Versi lama meminta LLM mengembalikan field yang tidak cocok dengan
CategorizedTransaction. Di sini kategorisasi dibuat deterministik dan konsisten
dengan rules engine v2.
"""

from core.finance_rules import classify_raw_transaction
from core.schemas import ParserOutput, CategorizerOutput


def _to_categorized(tx) -> dict:
    raw_hint = f"{tx.description} {tx.amount:.0f}"
    classified = classify_raw_transaction(raw_hint)
    entry = (classified.get("transactions") or [{}])[0]

    category = entry.get("category", "Lain-lain")
    accounting_type = entry.get("accounting_type", "other")
    if tx.type == "income" and entry.get("type") != "income":
        category = "Pendapatan Usaha"
        accounting_type = "revenue"

    return {
        "date": tx.date,
        "amount": tx.amount,
        "type": tx.type,
        "description": tx.description,
        "is_business": tx.is_business,
        "confidence": tx.confidence,
        "category": category,
        "sub_category": entry.get("sub_category", ""),
        "is_recurring": entry.get("is_recurring", False),
        "categorization_confidence": entry.get("confidence", 0.75),
        "is_cogs": accounting_type == "cogs",
        "is_asset_purchase": accounting_type in {"asset_purchase", "debt_payment", "receivable"},
    }


def run_categorizer_agent(parser_output: ParserOutput) -> CategorizerOutput:
    """
    Klasifikasi transaksi ParserOutput ke kategori bisnis yang valid.
    """
    transactions = [_to_categorized(tx) for tx in parser_output.transactions]
    total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
    total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
    categories_found = sorted({t["category"] for t in transactions if t.get("category")})
    recurring_count = sum(1 for t in transactions if t.get("is_recurring"))

    return CategorizerOutput(
        session_id=parser_output.session_id,
        transactions=transactions,
        total_income=total_income,
        total_expense=total_expense,
        categories_found=categories_found,
        recurring_count=recurring_count,
    )
