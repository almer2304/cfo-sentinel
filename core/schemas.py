"""
core/schemas.py
CFO Sentinel — Pydantic Schemas (Contract Antar Agent)

CHANGELOG:
- Fix HealthScore: ganti field_validator(mode='before') 
  ke model_validator(mode='after') — validator sekarang
  jalan setelah SEMUA field terisi, bukan sebelumnya
- Fix AnomalyOutput: sama, pindah ke model_validator
- Fix ConfidenceRange: tambah protection expected out-of-range
"""

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal


# ══════════════════════════════════════════════════════════════════
# SHARED
# ══════════════════════════════════════════════════════════════════

class ConfidenceRange(BaseModel):
    minimum:    float = Field(..., ge=0)
    expected:   float = Field(..., ge=0)
    maximum:    float = Field(..., ge=0)
    assumption: str   = ""

    @model_validator(mode="after")
    def validate_range(self):
        if self.maximum < self.minimum:
            self.maximum = self.minimum
        if self.expected < self.minimum:
            self.expected = self.minimum
        if self.expected > self.maximum:
            self.expected = self.maximum
        return self


# ══════════════════════════════════════════════════════════════════
# AGENT 1 — Parser Agent
# ══════════════════════════════════════════════════════════════════

class ParsedTransaction(BaseModel):
    date:                    str   = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount:                  float = Field(..., gt=0)
    type:                    Literal["income", "expense"]
    description:             str   = Field(..., min_length=1)
    is_business:             bool  = True
    confidence:              float = Field(default=1.0, ge=0.0, le=1.0)
    needs_clarification:     bool  = False
    clarification_question:  Optional[str] = None


class ParserOutput(BaseModel):
    session_id:       str
    transactions:     list[ParsedTransaction]
    raw_input:        str
    total_parsed:     int
    has_ambiguity:    bool        = False
    ambiguity_notes:  list[str]   = []

    @model_validator(mode="after")
    def sync_total_parsed(self):
        # Selalu sinkronkan total_parsed dengan panjang list aktual
        self.total_parsed = len(self.transactions)
        return self


# ══════════════════════════════════════════════════════════════════
# AGENT 2 — Categorizer Agent
# ══════════════════════════════════════════════════════════════════

VALID_CATEGORIES = [
    "Bahan Baku", "Operasional", "Marketing", "SDM",
    "Penjualan", "Piutang", "Utang", "Investasi", "Lain-lain",
]


class CategorizedTransaction(BaseModel):
    date:                       str
    amount:                     float
    type:                       Literal["income", "expense"]
    description:                str
    is_business:                bool  = True
    confidence:                 float = 1.0
    category:                   str
    sub_category:               str
    is_recurring:               bool  = False
    categorization_confidence:  float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v):
        if v not in VALID_CATEGORIES:
            # Jangan crash — fallback ke Lain-lain agar pipeline tidak berhenti
            return "Lain-lain"
        return v


class CategorizerOutput(BaseModel):
    session_id:       str
    transactions:     list[CategorizedTransaction]
    total_income:     float       = 0
    total_expense:    float       = 0
    categories_found: list[str]   = []
    recurring_count:  int         = 0


# ══════════════════════════════════════════════════════════════════
# AGENT 3 — Financial Analyst Agent
# ══════════════════════════════════════════════════════════════════

class HealthScore(BaseModel):
    current:            float = Field(..., ge=0, le=100)
    previous_month:     float = Field(default=0, ge=0, le=100)
    industry_average:   float = Field(default=0, ge=0, le=100)
    danger_threshold:   float = Field(default=50, ge=0, le=100)
    # status dan trend dihitung otomatis via model_validator
    status:             Literal["SAFE", "WARNING", "DANGER"] = "SAFE"
    trend:              Literal["UP", "DOWN", "STABLE"]       = "STABLE"

    @model_validator(mode="after")
    def compute_derived_fields(self):
        """
        Hitung status berdasarkan current vs threshold.
        Pakai model_validator(mode='after') agar SEMUA field
        sudah terisi saat validator jalan.

        FIX dari versi sebelumnya yang pakai field_validator(mode='before')
        — validator lama tidak bisa akses danger_threshold karena
        field diproses berurutan dan threshold belum ada saat
        status divalidasi.
        """
        score     = self.current
        threshold = self.danger_threshold

        if score < threshold:
            self.status = "DANGER"
        elif score < threshold + 15:
            self.status = "WARNING"
        else:
            self.status = "SAFE"

        # Hitung trend jika ada data bulan lalu
        if self.previous_month > 0:
            diff = self.current - self.previous_month
            if diff > 5:
                self.trend = "UP"
            elif diff < -5:
                self.trend = "DOWN"
            else:
                self.trend = "STABLE"

        return self


class ForecastPoint(BaseModel):
    day:                int
    date:               str
    predicted_balance:  float
    confidence_min:     float
    confidence_max:     float


class AnalystOutput(BaseModel):
    session_id:             str
    period_start:           str
    period_end:             str
    total_income:           float = 0
    total_expense:          float = 0
    net_cashflow:           float = 0
    cash_balance:           float = 0
    burn_rate_daily:        float = 0
    burn_rate_monthly:      float = 0
    gross_margin:           float = 0
    runway_days:            ConfidenceRange = Field(
        default_factory=lambda: ConfidenceRange(minimum=0, expected=0, maximum=0)
    )
    revenue_consistency:    float = 0
    health_score:           HealthScore
    forecast_30d:           list[ForecastPoint] = []
    narrative:              str   = ""
    business_type:          str   = "general"
    needs_reflection:       bool  = False
    reflection_note:        str   = ""


# ══════════════════════════════════════════════════════════════════
# AGENT 4 — Anomaly Detection Agent
# ══════════════════════════════════════════════════════════════════

class Anomaly(BaseModel):
    category:        str
    severity:        Literal["HIGH", "MEDIUM", "LOW"]
    current_amount:  float
    baseline_amount: float
    deviation_pct:   float
    description:     str
    suggested_action: str = ""

    @model_validator(mode="after")
    def compute_severity_from_deviation(self):
        """
        Auto-compute severity dari deviation_pct jika tidak valid.
        Juga memastikan severity konsisten dengan angka deviasi.
        """
        dev = abs(self.deviation_pct)
        if dev >= 100:
            self.severity = "HIGH"
        elif dev >= 50:
            self.severity = "MEDIUM"
        else:
            self.severity = "LOW"
        return self


class AnomalyOutput(BaseModel):
    session_id:             str
    anomalies:              list[Anomaly]   = []
    total_anomalies:        int             = 0
    high_severity_count:    int             = 0
    analyst_output_valid:   bool            = True
    analyst_correction:     Optional[str]   = None
    trigger_reflection:     bool            = False
    overall_risk_level:     Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"

    @model_validator(mode="after")
    def sync_counts(self):
        """
        Sinkronkan total_anomalies dan high_severity_count
        dengan data aktual — jangan percaya angka dari LLM.
        """
        self.total_anomalies     = len(self.anomalies)
        self.high_severity_count = sum(
            1 for a in self.anomalies if a.severity == "HIGH"
        )

        # Auto-compute risk level jika tidak ada anomali HIGH
        if self.high_severity_count > 0:
            self.overall_risk_level = "HIGH"
        elif self.total_anomalies > 2:
            self.overall_risk_level = "MEDIUM"
        elif self.total_anomalies > 0:
            self.overall_risk_level = "LOW"

        return self


# ══════════════════════════════════════════════════════════════════
# AGENT 5 — Scenario Simulation Agent
# ══════════════════════════════════════════════════════════════════

class CostItem(BaseModel):
    category:           str
    amount:             float
    is_cuttable:        bool
    cut_potential_pct:  float = 0
    rationale:          str   = ""


class ScenarioOutput(BaseModel):
    session_id:                 str
    scenario_type:              str
    parameter_name:             str
    parameter_change_pct:       float
    new_runway:                 ConfidenceRange
    new_health_score:           float
    breakeven_day:              Optional[int]       = None
    cuttable_costs:             list[CostItem]      = []
    fixed_costs:                list[CostItem]      = []
    total_cuttable_amount:      float               = 0
    chain_of_consequences:      str                 = ""
    mitigation_steps:           str                 = ""
    mitigation_impact:          str                 = ""


# ══════════════════════════════════════════════════════════════════
# AGENT 6 — Strategic Advisor Agent
# ══════════════════════════════════════════════════════════════════

class ActionItem(BaseModel):
    priority:           int     = Field(..., ge=1)
    title:              str
    description:        str
    urgency:            Literal["IMMEDIATE", "THIS_WEEK", "THIS_MONTH"]
    estimated_impact:   str     = ""
    category:           str     = ""


class EarlyWarning(BaseModel):
    message:            str
    days_until_crisis:  Optional[int]       = None
    confidence:         ConfidenceRange
    trigger_condition:  str


class AdvisorOutput(BaseModel):
    session_id:             str
    has_early_warning:      bool                        = False
    early_warning:          Optional[EarlyWarning]      = None
    action_items:           list[ActionItem]            = []
    executive_summary:      str
    detailed_advice:        str                         = ""
    uncertainty_statement:  str                         = ""
    conflict_detected:      bool                        = False
    conflict_resolution:    str                         = ""


# ══════════════════════════════════════════════════════════════════
# ORCHESTRATOR — Pipeline State
# ══════════════════════════════════════════════════════════════════

class PipelineState(BaseModel):
    """
    State yang dibawa Orchestrator sepanjang pipeline.
    Setiap agent baca dari sini dan tulis hasilnya ke sini.
    """
    session_id:             str
    raw_input:              str
    business_type:          str     = "general"
    current_cash_balance:   float   = 0

    parser_output:      Optional[ParserOutput]      = None
    categorizer_output: Optional[CategorizerOutput] = None
    analyst_output:     Optional[AnalystOutput]     = None
    anomaly_output:     Optional[AnomalyOutput]     = None
    scenario_output:    Optional[ScenarioOutput]    = None
    advisor_output:     Optional[AdvisorOutput]     = None

    reflection_count:   int     = 0
    max_reflection:     int     = 2
    current_step:       str     = "start"
    errors:             list[str] = []
    warnings:           list[str] = []
    is_demo_mode:       bool    = False

    class Config:
        # Izinkan arbitrary types untuk kompatibilitas LangGraph
        arbitrary_types_allowed = True


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT — Validation test
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Testing schemas...\n")

    # Test 1: HealthScore — validator harus jalan dengan benar
    h1 = HealthScore(current=45, danger_threshold=50, trend="DOWN")
    assert h1.status == "DANGER", f"Expected DANGER, got {h1.status}"
    print(f"✅ HealthScore DANGER: score=45, threshold=50 → {h1.status}")

    h2 = HealthScore(current=60, danger_threshold=50, trend="DOWN")
    assert h2.status == "WARNING", f"Expected WARNING, got {h2.status}"
    print(f"✅ HealthScore WARNING: score=60, threshold=50 → {h2.status}")

    h3 = HealthScore(current=80, danger_threshold=50, trend="UP")
    assert h3.status == "SAFE", f"Expected SAFE, got {h3.status}"
    print(f"✅ HealthScore SAFE: score=80, threshold=50 → {h3.status}")

    # Test 2: Trend auto-compute
    h4 = HealthScore(current=80, previous_month=60, danger_threshold=50)
    assert h4.trend == "UP", f"Expected UP, got {h4.trend}"
    print(f"✅ HealthScore trend UP: current=80, prev=60 → {h4.trend}")

    # Test 3: AnomalyOutput count sync
    # pyrefly: ignore [missing-import]
    from pydantic import ValidationError
    ao = AnomalyOutput(
        session_id="test",
        anomalies=[
            Anomaly(category="Operasional", severity="HIGH",
                    current_amount=4_000_000, baseline_amount=2_000_000,
                    deviation_pct=100, description="Test anomali"),
        ],
        total_anomalies=99,  # LLM beri angka salah
        high_severity_count=0,  # LLM beri angka salah
    )
    assert ao.total_anomalies == 1, f"Expected 1, got {ao.total_anomalies}"
    assert ao.high_severity_count == 1, f"Expected 1, got {ao.high_severity_count}"
    print(f"✅ AnomalyOutput sync: total={ao.total_anomalies}, high={ao.high_severity_count}")

    # Test 4: ConfidenceRange auto-fix
    cr = ConfidenceRange(minimum=10, expected=5, maximum=3)  # semua salah
    assert cr.minimum <= cr.expected <= cr.maximum
    print(f"✅ ConfidenceRange auto-fix: {cr.minimum}-{cr.expected}-{cr.maximum}")

    # Test 5: Category validator fallback
    ct = CategorizedTransaction(
        date="2026-05-09", amount=100_000, type="expense",
        description="test", category="KategoriTidakAda",
        sub_category="Lainnya"
    )
    assert ct.category == "Lain-lain"
    print(f"✅ Category fallback: 'KategoriTidakAda' → '{ct.category}'")

    print("\n✅ All schema tests passed!")