from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from api.models.request import AnalysisRequest
from api.models.response import (
    AnalysisResponse, HealthScoreData, MetricsData,
    AnomalyData, ActionItemData, EarlyWarningData,
    ScenarioData, ForecastPointData, AgentLogData,
)
from api.middleware.auth import get_current_user
from core.orchestrator import run_pipeline
from core.database import get_agent_logs

router = APIRouter(prefix="/analysis", tags=["Analysis"])


def _build_analysis_response(result, session_id: str) -> AnalysisResponse:
    """Convert PipelineState ke AnalysisResponse."""

    analyst  = result.analyst_output
    anomaly  = result.anomaly_output
    advisor  = result.advisor_output
    scenario = result.scenario_output

    if not analyst:
        raise HTTPException(
            status_code=500,
            detail="Pipeline gagal menganalisis. Coba lagi."
        )

    hs = analyst.health_score
    health_data = HealthScoreData(
        current=hs.current,
        previous_month=hs.previous_month,
        industry_average=hs.industry_average,
        danger_threshold=hs.danger_threshold,
        status=hs.status,
        trend=hs.trend,
    )

    metrics_data = MetricsData(
        total_income=analyst.total_income,
        total_expense=analyst.total_expense,
        net_cashflow=analyst.net_cashflow,
        cash_balance=analyst.cash_balance,
        burn_rate_daily=analyst.burn_rate_daily,
        burn_rate_monthly=analyst.burn_rate_monthly,
        net_margin=analyst.net_margin,
        runway_min=analyst.runway_days.minimum,
        runway_expected=analyst.runway_days.expected,
        runway_max=analyst.runway_days.maximum,
        revenue_consistency=analyst.revenue_consistency,
    )

    anomaly_list = []
    overall_risk = "LOW"
    if anomaly:
        overall_risk = anomaly.overall_risk_level
        for a in anomaly.anomalies:
            anomaly_list.append(AnomalyData(
                category=a.category,
                severity=a.severity,
                current_amount=a.current_amount,
                baseline_amount=a.baseline_amount,
                deviation_pct=a.deviation_pct,
                description=a.description,
                suggested_action=a.suggested_action,
            ))

    has_warning = False
    early_warning = None
    action_items = []
    executive_summary = ""
    detailed_advice = ""
    uncertainty = ""

    if advisor:
        has_warning = advisor.has_early_warning
        executive_summary = advisor.executive_summary
        detailed_advice = advisor.detailed_advice
        uncertainty = advisor.uncertainty_statement

        if advisor.has_early_warning and advisor.early_warning:
            ew = advisor.early_warning
            early_warning = EarlyWarningData(
                message=ew.message,
                days_until_crisis=ew.days_until_crisis,
                trigger_condition=ew.trigger_condition,
            )

        for item in advisor.action_items:
            action_items.append(ActionItemData(
                priority=item.priority,
                title=item.title,
                description=item.description,
                urgency=item.urgency,
                estimated_impact=item.estimated_impact,
            ))

    scenario_data = None
    if scenario:
        scenario_data = ScenarioData(
            scenario_type=scenario.scenario_type,
            parameter_change_pct=scenario.parameter_change_pct,
            new_runway_expected=scenario.new_runway.expected,
            new_health_score=scenario.new_health_score,
            chain_of_consequences=scenario.chain_of_consequences,
            mitigation_steps=scenario.mitigation_steps,
            total_cuttable_amount=scenario.total_cuttable_amount,
        )

    forecast_list = [
        ForecastPointData(
            day=fp.day,
            date=fp.date,
            predicted_balance=fp.predicted_balance,
            confidence_min=fp.confidence_min,
            confidence_max=fp.confidence_max,
        )
        for fp in analyst.forecast_30d
    ]

    raw_logs = get_agent_logs(session_id)
    agent_logs = [
        AgentLogData(
            agent_name=log["agent_name"],
            step=log["step"],
            input_summary=log.get("input_summary", ""),
            reasoning=log.get("reasoning", ""),
            output_summary=log.get("output_summary", ""),
            duration_ms=log.get("duration_ms", 0),
            status=log.get("status", "success"),
        )
        for log in raw_logs
    ]

    return AnalysisResponse(
        success=True,
        session_id=session_id,
        health_score=health_data,
        metrics=metrics_data,
        narrative=analyst.narrative,
        anomalies=anomaly_list,
        overall_risk_level=overall_risk,
        has_early_warning=has_warning,
        early_warning=early_warning,
        action_items=action_items,
        executive_summary=executive_summary,
        detailed_advice=detailed_advice,
        uncertainty_statement=uncertainty,
        scenario=scenario_data,
        forecast_30d=forecast_list,
        agent_logs=agent_logs,
    )


@router.post("/run", response_model=AnalysisResponse)
async def run_analysis(
    request: AnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Jalankan full pipeline analisis keuangan.
    Ini endpoint utama yang dipanggil saat user submit transaksi.
    """
    try:
        result = run_pipeline(
            raw_input=request.raw_input,
            business_type=request.business_type,
            current_cash_balance=request.current_cash_balance,
            user_id=current_user["id"],
        )
        return _build_analysis_response(result, result.session_id)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analisis gagal: {str(e)}"
        )
