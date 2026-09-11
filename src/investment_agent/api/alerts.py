from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.market_data.volume import extract_daily_volumes
from investment_agent.portfolio.alerts import evaluate_market_alerts
from investment_agent.repositories import (
    MarketAlertRepository,
    PortfolioRepository,
    UserProfileRepository,
)
from investment_agent.storage import MarketAlertSettings, MarketAlertSnapshot

router = APIRouter(prefix="/portfolio/alerts", tags=["portfolio-alerts"])


class AlertSettingsRequest(BaseModel):
    enabled: bool = True
    delivery_mode: str = Field(default="preview_only", pattern="^preview_only$")
    scope: str = Field(default="holdings", pattern="^holdings$")
    sensitivity: str = Field(default="standard", pattern="^(conservative|standard|active)$")
    timezone: str = Field(default="America/Los_Angeles", min_length=1, max_length=64)
    quiet_hours_start: str = Field(default="21:00", pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")


class AlertSettingsResponse(BaseModel):
    enabled: bool
    delivery_mode: str
    scope: str
    sensitivity: str
    timezone: str
    quiet_hours_start: str
    quiet_hours_end: str
    policy_version: int
    telegram_available: bool = False


class AlertSnapshotResponse(BaseModel):
    id: int
    symbol: str
    direction: str
    severity: str
    score: int
    policy_version: int
    status: str
    holding_quantity: float
    portfolio_weight: float
    latest_close: float
    market_as_of_date: str
    holdings_as_of_date: str
    reasons: list[str]
    counter_evidence: list[str]
    invalidation_conditions: list[str]
    warnings: list[str]
    metrics: dict[str, object]
    feedback: str | None
    feedback_action: str | None
    created_at: datetime


class AlertListResponse(BaseModel):
    settings: AlertSettingsResponse
    alerts: list[AlertSnapshotResponse]


class AlertEvaluationResponse(BaseModel):
    created_count: int
    suppressed_count: int
    evaluated_symbols: int
    alerts: list[AlertSnapshotResponse]


class AlertFeedbackRequest(BaseModel):
    feedback: str = Field(pattern="^(useful|noise|too_late|incorrect)$")


@router.get("", response_model=AlertListResponse)
def list_alerts(session: Session = Depends(get_db_session)) -> AlertListResponse:
    repository = MarketAlertRepository(session)
    return AlertListResponse(
        settings=_settings_response(repository.settings()),
        alerts=[_snapshot_response(item) for item in repository.list_snapshots()],
    )


@router.put("/settings", response_model=AlertSettingsResponse)
def update_alert_settings(
    payload: AlertSettingsRequest,
    session: Session = Depends(get_db_session),
) -> AlertSettingsResponse:
    settings = MarketAlertRepository(session).save_settings(**payload.model_dump())
    return _settings_response(settings)


@router.post("/evaluate", response_model=AlertEvaluationResponse)
def evaluate_alerts(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AlertEvaluationResponse:
    repository = MarketAlertRepository(session)
    settings = repository.settings()
    if not settings.enabled:
        raise HTTPException(status_code=409, detail="Market review previews are paused.")
    gateway = getattr(request.app.state, "robinhood_gateway", None)
    if gateway is None:
        raise HTTPException(status_code=409, detail="Robinhood read-only data is not connected.")
    app_settings = request.app.state.settings
    if not app_settings.robinhood_enable_historicals:
        raise HTTPException(status_code=409, detail="Robinhood historical data is disabled.")
    positions = PortfolioRepository(session).list_positions()
    if not positions:
        raise HTTPException(status_code=409, detail="Refresh or import holdings before evaluating alerts.")
    symbols = sorted({item.symbol.strip().upper() for item in positions if item.symbol.strip()})
    now = datetime.now(timezone.utc)
    try:
        payload = gateway.read_historicals(
            symbols,
            start_time=(now - timedelta(days=190)).isoformat(),
            end_time=now.isoformat(),
            interval="day",
            bounds="regular",
            adjustment_type="split",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Robinhood historical data is unavailable.") from exc
    histories = extract_daily_volumes(
        payload,
        requested_symbols=symbols,
        exclude_on_or_after=now.date(),
    )
    profile = UserProfileRepository(session).get_active_profile()
    decisions = evaluate_market_alerts(
        positions,
        histories,
        target_allocation=(profile.target_allocation_json if profile else {}),
        rebalance_threshold=(float(profile.rebalance_threshold) if profile else 0.05),
        sensitivity=settings.sensitivity,
    )
    created = [
        item
        for decision in decisions
        if (item := repository.add_decision(decision, policy_version=settings.policy_version))
        is not None
    ]
    return AlertEvaluationResponse(
        created_count=len(created),
        suppressed_count=len(decisions) - len(created),
        evaluated_symbols=len(symbols),
        alerts=[_snapshot_response(item) for item in created],
    )


@router.post("/{snapshot_id}/feedback", response_model=AlertSnapshotResponse)
def submit_feedback(
    snapshot_id: int,
    payload: AlertFeedbackRequest,
    session: Session = Depends(get_db_session),
) -> AlertSnapshotResponse:
    snapshot = MarketAlertRepository(session).feedback(snapshot_id, payload.feedback)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Alert preview not found.")
    return _snapshot_response(snapshot)


def _settings_response(value: MarketAlertSettings) -> AlertSettingsResponse:
    return AlertSettingsResponse(
        enabled=value.enabled,
        delivery_mode=value.delivery_mode,
        scope=value.scope,
        sensitivity=value.sensitivity,
        timezone=value.timezone,
        quiet_hours_start=value.quiet_hours_start,
        quiet_hours_end=value.quiet_hours_end,
        policy_version=value.policy_version,
    )


def _snapshot_response(value: MarketAlertSnapshot) -> AlertSnapshotResponse:
    return AlertSnapshotResponse(
        id=value.id,
        symbol=value.symbol,
        direction=value.direction,
        severity=value.severity,
        score=value.score,
        policy_version=value.policy_version,
        status=value.status,
        holding_quantity=value.holding_quantity,
        portfolio_weight=value.portfolio_weight,
        latest_close=value.latest_close,
        market_as_of_date=value.market_as_of_date.isoformat(),
        holdings_as_of_date=value.holdings_as_of_date.isoformat(),
        reasons=list(value.reasons_json),
        counter_evidence=list(value.counter_evidence_json),
        invalidation_conditions=list(value.invalidation_conditions_json),
        warnings=list(value.warnings_json),
        metrics=dict(value.metrics_json),
        feedback=value.feedback,
        feedback_action=value.feedback_action,
        created_at=value.created_at,
    )
