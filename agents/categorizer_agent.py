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
    if getattr(tx, "accounting_type", None) and getattr(tx, "debit_account", None) and getattr(tx, "credit_account", None):
        entry = {
            "category": tx.category or "Lain-lain",
            "sub_category": tx.sub_category or "",
            "accounting_type": tx.accounting_type or "other",
            "debit_account": tx.debit_account or "",
            "credit_account": tx.credit_account or "",
            "is_pnl": tx.is_pnl if tx.is_pnl is not None else True,
            "is_recurring": False,
            "confidence": tx.confidence,
            "type": tx.type,
        }
    else:
        raw_hint = f"{tx.description} Rp {tx.amount:.0f}"
        classified = classify_raw_transaction(raw_hint)
        entry = (classified.get("transactions") or [{}])[0]

    category = entry.get("category", "Lain-lain")
    accounting_type = entry.get("accounting_type", "other")
    if tx.type == "income" and entry.get("type") != "income":
        category = "Pendapatan Usaha"
        accounting_type = "revenue"
        entry["debit_account"] = "Kas"
        entry["credit_account"] = "Pendapatan Usaha"
        entry["is_pnl"] = True

    return {
        "date": tx.date,
        "amount": tx.amount,
        "type": tx.type,
        "description": tx.description,
        "is_business": tx.is_business,
        "confidence": tx.confidence,
        "category": category,
        "sub_category": entry.get("sub_category", ""),
        "accounting_type": accounting_type,
        "debit_account": entry.get("debit_account", ""),
        "credit_account": entry.get("credit_account", ""),
        "is_pnl": entry.get("is_pnl", True),
        "is_recurring": entry.get("is_recurring", False),
        "categorization_confidence": entry.get("confidence", 0.75),
        "is_cogs": accounting_type == "cogs",
        "is_asset_purchase": (
            accounting_type == "asset_purchase"
            or (tx.type == "expense" and not entry.get("is_pnl", True))
        ),
    }


def _is_cash_in(tx: dict) -> bool:
    return tx.get("debit_account") == "Kas" or (
        not tx.get("debit_account") and tx.get("type") == "income"
    )


def _is_cash_out(tx: dict) -> bool:
    return tx.get("credit_account") == "Kas" or (
        not tx.get("credit_account") and tx.get("type") == "expense"
    )


def _is_journal_revenue(tx: dict) -> bool:
    return (
        tx.get("accounting_type") == "revenue"
        or tx.get("credit_account") in {"Pendapatan Usaha", "Pendapatan Lain"}
    )


def _is_journal_expense(tx: dict) -> bool:
    debit = tx.get("debit_account") or ""
    return (
        tx.get("accounting_type") in {"operational_expense", "cogs"}
        or debit.startswith("Beban")
        or debit == "HPP (Bahan Baku)"
    )


def run_categorizer_agent(parser_output: ParserOutput) -> CategorizerOutput:
    """
    Klasifikasi transaksi ParserOutput ke kategori bisnis yang valid.
    """
    transactions = [_to_categorized(tx) for tx in parser_output.transactions]
    total_cash_in = sum(t["amount"] for t in transactions if _is_cash_in(t))
    total_cash_out = sum(t["amount"] for t in transactions if _is_cash_out(t))
    journal_revenue = sum(t["amount"] for t in transactions if _is_journal_revenue(t))
    journal_expense = sum(t["amount"] for t in transactions if _is_journal_expense(t))
    categories_found = sorted({t["category"] for t in transactions if t.get("category")})
    recurring_count = sum(1 for t in transactions if t.get("is_recurring"))

    return CategorizerOutput(
        session_id=parser_output.session_id,
        transactions=transactions,
        total_income=total_cash_in,
        total_expense=total_cash_out,
        total_cash_in=total_cash_in,
        total_cash_out=total_cash_out,
        journal_revenue=journal_revenue,
        journal_expense=journal_expense,
        categories_found=categories_found,
        recurring_count=recurring_count,
    )
