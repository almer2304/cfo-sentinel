"""
agents/categorizer_agent.py
CFO Sentinel — Categorizer Agent
"""

from core.llm_client import call_llm_json
from core.prompts import get_categorizer_prompt
from core.schemas import ParserOutput, CategorizerOutput

def run_categorizer_agent(parser_output: ParserOutput) -> CategorizerOutput:
    """
    Menjalankan Categorizer Agent (Bookkeeper) untuk mengklasifikasi transaksi.
    """
    system_prompt = get_categorizer_prompt()
    
    # Input ke LLM adalah transaksi dari ParserOutput
    user_message = parser_output.model_dump_json(include={"transactions"})
    
    parsed_json, metadata = call_llm_json(
        agent_name="bookkeeper",
        system_prompt=system_prompt,
        user_message=user_message
    )
    
    transactions = parsed_json.get("transactions", [])
    categories_found = parsed_json.get("categories_found", [])
    recurring_count = parsed_json.get("recurring_count", 0)
    
    # Calculate totals and normalize fields
    total_income = 0
    total_expense = 0
    
    for t in transactions:
        amount = t.get("amount", 0)
        t_type = t.get("type", "expense")
        
        if t_type == "income":
            total_income += amount
        else:
            total_expense += amount
            
        # Pastikan is_asset_purchase terisi dari COA atau is_pnl
        if t.get("is_asset_purchase") is None:
            t["is_asset_purchase"] = not t.get("is_pnl", True)

    output = CategorizerOutput(
        session_id=parser_output.session_id,
        transactions=transactions,
        total_income=total_income,
        total_expense=total_expense,
        categories_found=categories_found,
        recurring_count=recurring_count
    )
    
    return output
