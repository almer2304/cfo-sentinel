from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    business_name: str
    email: str
    password: str
    business_type: str = "general"

class AnalysisRequest(BaseModel):
    raw_input: str
    business_type: str = "general"
    current_cash_balance: float = 0.0

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
