from pydantic import BaseModel
from typing import Optional, Any

class BaseResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[Any] = None

class UserData(BaseModel):
    id: int
    business_name: str
    email: str
    business_type: str
    total_sessions: int = 0
    avg_health_score: float = 0

class TokenResponse(BaseModel):
    success: bool
    token: str
    user: UserData

class HealthScoreData(BaseModel):
    current: float
    previous_month: float
    industry_average: float
    danger_threshold: float
    status: str      # SAFE, WARNING, DANGER
    trend: str       # UP, DOWN, STABLE

class MetricsData(BaseModel):
    total_income: float
    total_expense: float
    net_cashflow: float
    cash_balance: float
    burn_rate_daily: float
    burn_rate_monthly: float
    net_margin: float
    runway_min: float
    runway_expected: float
    runway_max: float
    revenue_consistency: float

class AnomalyData(BaseModel):
    category: str
    severity: str
    current_amount: float
    baseline_amount: float
    deviation_pct: float
    description: str
    suggested_action: str = ""

class ActionItemData(BaseModel):
    priority: int
    title: str
    description: str
    urgency: str
    estimated_impact: str = ""

class EarlyWarningData(BaseModel):
    message: str
    days_until_crisis: Optional[int]
    trigger_condition: str

class ScenarioData(BaseModel):
    scenario_type: str
    parameter_change_pct: float
    new_runway_expected: float
    new_health_score: float
    chain_of_consequences: str
    mitigation_steps: str
    total_cuttable_amount: float

class ForecastPointData(BaseModel):
    day: int
    date: str
    predicted_balance: float
    confidence_min: float
    confidence_max: float

class AgentLogData(BaseModel):
    agent_name: str
    step: int
    input_summary: str
    reasoning: str
    output_summary: str
    duration_ms: int
    status: str

class AnalysisResponse(BaseModel):
    success: bool
    session_id: str
    health_score: HealthScoreData
    metrics: MetricsData
    narrative: str
    anomalies: list[AnomalyData]
    overall_risk_level: str
    has_early_warning: bool
    early_warning: Optional[EarlyWarningData]
    action_items: list[ActionItemData]
    executive_summary: str
    detailed_advice: str
    uncertainty_statement: str
    scenario: Optional[ScenarioData]
    forecast_30d: list[ForecastPointData]
    agent_logs: list[AgentLogData]

class HistoryItem(BaseModel):
    session_id: str
    created_at: str
    health_score: float
    health_status: str
    total_income: float
    total_expense: float
    net_cashflow: float
    cash_balance: float
    runway_days: float
    narrative: str
    anomalies: list[AnomalyData] = []
    action_items: list[ActionItemData] = []

class ChatResponse(BaseModel):
    success: bool
    answer: str
    session_id: Optional[str]
