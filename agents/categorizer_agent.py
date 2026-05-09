"""
agents/categorizer_agent.py
CFO Sentinel — Categorizer Agent
"""

from core.llm_client import call_llm_json
from core.prompts import get_categorizer_prompt
from core.schemas import ParserOutput, CategorizerOutput

def run_categorizer_agent(parser_output: ParserOutput) -> CategorizerOutput:
    """
    Menjalankan Categorizer Agent untuk mengklasifikasi transaksi.
    """
    system_prompt = get_categorizer_prompt()
    
    # Input ke LLM adalah transaksi dari ParserOutput
    user_message = parser_output.model_dump_json(include={"transactions"})
    
    parsed_json, metadata = call_llm_json(
        agent_name="categorizer",
        system_prompt=system_prompt,
        user_message=user_message
    )
    
    transactions = parsed_json.get("transactions", [])
    categories_found = parsed_json.get("categories_found", [])
    recurring_count = parsed_json.get("recurring_count", 0)
    
    # Calculate totals manually
    total_income = sum(t.get("amount", 0) for t in transactions if t.get("type") == "income")
    total_expense = sum(t.get("amount", 0) for t in transactions if t.get("type") == "expense")
    
    output = CategorizerOutput(
        session_id=parser_output.session_id,
        transactions=transactions,
        total_income=total_income,
        total_expense=total_expense,
        categories_found=categories_found,
        recurring_count=recurring_count
    )
    
    return output
