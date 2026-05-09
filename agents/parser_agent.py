"""
agents/parser_agent.py
CFO Sentinel — Parser Agent
"""

from core.llm_client import call_llm_json
from core.prompts import get_parser_prompt
from core.schemas import ParserOutput

def run_parser_agent(session_id: str, raw_input: str) -> ParserOutput:
    """
    Menjalankan Parser Agent untuk mengubah input teks menjadi JSON terstruktur.
    """
    system_prompt = get_parser_prompt()
    
    parsed_json, metadata = call_llm_json(
        agent_name="parser",
        system_prompt=system_prompt,
        user_message=raw_input
    )
    
    transactions = parsed_json.get("transactions", [])
    
    # Validasi Pydantic Schema secara otomatis saat inisialisasi model
    output = ParserOutput(
        session_id=session_id,
        raw_input=raw_input,
        transactions=transactions,
        total_parsed=len(transactions),
        has_ambiguity=parsed_json.get("has_ambiguity", False),
        ambiguity_notes=parsed_json.get("ambiguity_notes", [])
    )
    
    return output
