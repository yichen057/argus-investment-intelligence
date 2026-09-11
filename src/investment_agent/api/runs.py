from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.billing import (
    DeepSeekExportError,
    ProviderBalance,
    ProviderBalanceError,
    fetch_deepseek_balance,
    fetch_kimi_balance,
    parse_deepseek_usage_export,
)
from investment_agent.repositories import (
    AgentRunRepository,
    EventAuditRepository,
    ProviderAccountSnapshotCreate,
    ProviderBillingSnapshotCreate,
)
from investment_agent.repositories.runs import (
    ApiUsageAggregate,
    ModelCallAggregate,
    UsageTotals,
)
from investment_agent.storage import (
    AgentRun,
    ModelCall,
    ProviderAccountSnapshot,
    ProviderBillingSnapshot,
    ToolCallRecord,
)

_MAX_PROVIDER_EXPORT_BYTES = 5 * 1024 * 1024

router = APIRouter(prefix="/runs", tags=["runs"])


class ModelBreakdownResponse(BaseModel):
    provider: str
    model: str
    deployment: str
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_estimated_cost_usd: float
    avg_latency_ms: float | None
    input_cost_per_million_usd: float | None = None
    output_cost_per_million_usd: float | None = None


class UsageSummaryResponse(BaseModel):
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_estimated_cost_usd: float
    first_recorded_at: datetime | None
    last_recorded_at: datetime | None


class ProviderBillingSnapshotResponse(BaseModel):
    id: int
    provider: str
    period_start: date
    period_end: date
    currency: str
    actual_cost: float
    total_tokens: int | None
    request_count: int | None
    source_reference: str | None
    metadata: dict[str, Any]
    created_at: datetime


class ProviderBillingSnapshotRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=128)
    period_start: date
    period_end: date
    currency: str = Field(min_length=3, max_length=8)
    actual_cost: Decimal = Field(ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    request_count: int | None = Field(default=None, ge=0)
    source_reference: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderAccountSnapshotResponse(BaseModel):
    id: int
    provider: str
    billing_tier: str | None
    billing_status: str
    currency: str | None
    available_balance: float | None
    paid_balance: float | None
    promotional_balance: float | None
    source_reference: str | None
    metadata: dict[str, Any]
    created_at: datetime


class ProviderAccountSnapshotRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=128)
    billing_tier: str | None = Field(default=None, max_length=64)
    billing_status: str = Field(min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    available_balance: Decimal | None = Field(default=None, ge=0)
    paid_balance: Decimal | None = Field(default=None, ge=0)
    promotional_balance: Decimal | None = Field(default=None, ge=0)
    source_reference: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderBalanceRefreshItemResponse(BaseModel):
    provider: str
    status: str
    message: str
    snapshot: ProviderAccountSnapshotResponse | None = None


class ProviderBalanceRefreshResponse(BaseModel):
    refreshed_at: datetime
    updated_count: int
    results: list[ProviderBalanceRefreshItemResponse]


class RunSummaryResponse(BaseModel):
    id: int
    run_key: str
    role: str
    objective: str
    status: str
    sensitivity: str
    as_of_date: date | None
    selection_mode: str
    selected_model: str | None
    selection_reason: str | None
    total_tokens: int
    total_estimated_cost_usd: float
    model_call_count: int
    tool_call_count: int
    created_at: datetime


class EventPipelineEventResponse(BaseModel):
    event_id: str
    event_type: str
    aggregate_id: str
    status: str
    attempt_count: int
    duplicate_count: int
    topic: str
    partition: int | None
    message_offset: int | None
    occurred_at: datetime | None
    processed_at: datetime
    error_code: str | None
    failure_code: str | None
    run_status: str | None
    execution_outcome: str | None
    answer_generated: bool | None
    provider: str | None
    model: str | None
    failure_stage: str | None


class EventPipelineResponse(BaseModel):
    configured: bool
    transport: str
    consumer_group: str
    consumer_status: str
    last_heartbeat_at: datetime | None
    last_error_code: str | None
    processed_count: int
    completed_count: int
    answer_generated_count: int
    safe_stop_count: int
    failed_count: int
    duplicate_count: int
    dlq_count: int
    recent_events: list[EventPipelineEventResponse]
    scope_note: str


class RunsDashboardResponse(BaseModel):
    total_runs: int
    total_tokens: int
    total_estimated_cost_usd: float
    failed_runs: int
    model_call_count: int
    tool_call_count: int
    model_breakdown: list[ModelBreakdownResponse]
    retained_run_usage: UsageSummaryResponse
    historical_api_usage: UsageSummaryResponse
    historical_model_breakdown: list[ModelBreakdownResponse]
    provider_billing_snapshots: list[ProviderBillingSnapshotResponse]
    provider_account_snapshots: list[ProviderAccountSnapshotResponse]
    historical_usage_scope_note: str
    event_pipeline: EventPipelineResponse
    recent_runs: list[RunSummaryResponse]
    limit: int
    offset: int
    has_more: bool


class ModelCallResponse(BaseModel):
    id: int
    provider: str
    model: str
    deployment: str
    serving_engine: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: int | None
    success: bool
    created_at: datetime


class ToolCallResponse(BaseModel):
    id: int
    call_id: str
    tool_name: str
    status: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    error_code: str | None
    latency_ms: int | None
    created_at: datetime


class EvidenceLedgerQueryResponse(BaseModel):
    id: int
    round_number: int
    target_slot: str
    query: str
    search_mode: str
    channel_counts: dict[str, int]
    result_count: int


class EvidenceLedgerLinkResponse(BaseModel):
    query_id: int
    chunk_id: int | None
    evidence_item_id: int | None
    accepted: bool
    fused_score: float | None
    match_signals: list[str]
    channel_ranks: dict[str, int]


class RunDetailResponse(BaseModel):
    run: RunSummaryResponse
    model_calls: list[ModelCallResponse]
    tool_calls: list[ToolCallResponse]
    evidence_ledger_queries: list[EvidenceLedgerQueryResponse]
    evidence_ledger_links: list[EvidenceLedgerLinkResponse]
    decision_trace: dict[str, Any] | None


@router.get("", response_model=RunsDashboardResponse)
def list_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> RunsDashboardResponse:
    repository = AgentRunRepository(session)
    recent_runs = repository.list_runs(limit=limit, offset=offset)
    total_run_count, total_tokens, total_cost, failed_runs = repository.run_totals()
    recent_run_ids = {run.id for run in recent_runs}
    model_calls = repository.list_model_calls(run_ids=recent_run_ids)
    tool_calls = repository.list_tool_calls(run_ids=recent_run_ids)
    call_counts = _call_counts(
        runs=recent_runs,
        model_calls=model_calls,
        tool_calls=tool_calls,
    )
    retained_usage = repository.retained_model_usage_totals()
    historical_usage = repository.api_usage_totals()
    provider_snapshots = repository.list_provider_billing_snapshots()
    provider_account_snapshots = repository.list_latest_provider_account_snapshots()
    event_pipeline = _event_pipeline_response(
        request=request,
        repository=EventAuditRepository(session),
    )

    return RunsDashboardResponse(
        total_runs=total_run_count,
        total_tokens=total_tokens,
        total_estimated_cost_usd=total_cost,
        failed_runs=failed_runs,
        model_call_count=repository.count_model_calls(),
        tool_call_count=repository.count_tool_calls(),
        model_breakdown=_model_breakdown(repository.model_call_breakdown()),
        retained_run_usage=_usage_summary(retained_usage),
        historical_api_usage=_usage_summary(historical_usage),
        historical_model_breakdown=_api_usage_breakdown(
            repository.api_usage_breakdown()
        ),
        provider_billing_snapshots=[
            _provider_billing_snapshot_response(snapshot)
            for snapshot in provider_snapshots
        ],
        provider_account_snapshots=[
            _provider_account_snapshot_response(snapshot)
            for snapshot in provider_account_snapshots
        ],
        historical_usage_scope_note=(
            "Includes calls recorded after API Usage Ledger adoption plus ModelCall "
            "rows that still existed during migration 0019. Usage deleted before that "
            "migration cannot be reconstructed without a provider export."
        ),
        event_pipeline=event_pipeline,
        recent_runs=[_run_summary(run, call_counts=call_counts) for run in recent_runs],
        limit=limit,
        offset=offset,
        has_more=offset + len(recent_runs) < total_run_count,
    )


def _event_pipeline_response(
    *,
    request: Request,
    repository: EventAuditRepository,
) -> EventPipelineResponse:
    settings = request.app.state.settings
    configured = bool(settings.kafka_bootstrap_servers)
    heartbeat = repository.get_heartbeat(settings.kafka_consumer_group)
    totals = repository.totals()
    # Return a bounded two-page set for the UI's 10-row pagination. The audit
    # repository still enforces its separate retention policy.
    recent = repository.list_recent(limit=20)
    status_value = "disabled" if not configured else "waiting"
    last_seen = None
    last_error = None
    if configured and heartbeat is not None:
        last_seen = heartbeat.last_seen_at
        last_error = heartbeat.last_error_code
        comparable_last_seen = last_seen
        if comparable_last_seen.tzinfo is None:
            comparable_last_seen = comparable_last_seen.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - comparable_last_seen).total_seconds()
        if age_seconds > settings.kafka_consumer_stale_after_seconds:
            status_value = "stale"
        else:
            status_value = heartbeat.status
    return EventPipelineResponse(
        configured=configured,
        transport="kafka" if configured else "in-memory fallback",
        consumer_group=settings.kafka_consumer_group,
        consumer_status=status_value,
        last_heartbeat_at=last_seen,
        last_error_code=last_error,
        processed_count=totals.processed_count,
        completed_count=totals.completed_count,
        answer_generated_count=totals.answer_generated_count,
        safe_stop_count=totals.safe_stop_count,
        failed_count=totals.failed_count,
        duplicate_count=totals.duplicate_count,
        dlq_count=totals.dlq_count,
        recent_events=[
            EventPipelineEventResponse(
                event_id=record.event_id,
                event_type=record.event_type,
                aggregate_id=record.aggregate_id,
                status=record.status,
                attempt_count=record.attempt_count,
                duplicate_count=record.duplicate_count,
                topic=record.topic,
                partition=record.partition,
                message_offset=record.message_offset,
                occurred_at=record.occurred_at,
                processed_at=record.updated_at,
                error_code=record.error_code,
                failure_code=_payload_summary_string(
                    record.payload_summary_json,
                    "error_code",
                ),
                run_status=_payload_summary_string(
                    record.payload_summary_json,
                    "status",
                ),
                execution_outcome=_payload_summary_string(
                    record.payload_summary_json,
                    "execution_outcome",
                ),
                answer_generated=_payload_summary_bool(
                    record.payload_summary_json,
                    "answer_generated",
                ),
                provider=_payload_summary_string(
                    record.payload_summary_json,
                    "provider",
                ),
                model=_payload_summary_string(
                    record.payload_summary_json,
                    "model",
                ),
                failure_stage=_payload_summary_string(
                    record.payload_summary_json,
                    "failure_stage",
                ),
            )
            for record in recent
        ],
        scope_note=(
            "Operational Kafka evidence only. PostgreSQL Runs remain the source of "
            "truth; raw payloads, prompts, holdings, documents, and API keys are not "
            "stored in this projection."
        ),
    )


def _payload_summary_string(payload: object, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _payload_summary_bool(payload: object, key: str) -> bool | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return value if isinstance(value, bool) else None


@router.post(
    "/provider-billing-snapshots",
    response_model=ProviderBillingSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_billing_snapshot(
    payload: ProviderBillingSnapshotRequest,
    session: Session = Depends(get_db_session),
) -> ProviderBillingSnapshotResponse:
    """Store a provider-reported aggregate without prompts, holdings, or API keys."""

    if payload.period_end < payload.period_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="period_end must be on or after period_start",
        )
    repository = AgentRunRepository(session)
    snapshot = repository.record_provider_billing_snapshot(
        ProviderBillingSnapshotCreate(
            provider=payload.provider.strip().lower(),
            period_start=payload.period_start,
            period_end=payload.period_end,
            currency=payload.currency.strip().upper(),
            actual_cost=payload.actual_cost,
            total_tokens=payload.total_tokens,
            request_count=payload.request_count,
            source_reference=(
                payload.source_reference.strip()
                if payload.source_reference and payload.source_reference.strip()
                else None
            ),
            metadata={
                "import_kind": "manual_provider_summary",
                **payload.metadata,
            },
        )
    )
    return _provider_billing_snapshot_response(snapshot)


@router.post(
    "/provider-billing-snapshots/import/deepseek",
    response_model=ProviderBillingSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_deepseek_provider_billing_snapshot(
    request: Request,
    x_argus_filename: str = Header(alias="X-Argus-Filename"),
    session: Session = Depends(get_db_session),
) -> ProviderBillingSnapshotResponse:
    """Import a bounded official DeepSeek ZIP without retaining identity columns."""

    filename = PurePath(x_argus_filename).name
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_PROVIDER_EXPORT_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="The DeepSeek export exceeds the 5 MB import limit.",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The upload Content-Length header is invalid.",
            ) from exc

    archive = bytearray()
    async for chunk in request.stream():
        archive.extend(chunk)
        if len(archive) > _MAX_PROVIDER_EXPORT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="The DeepSeek export exceeds the 5 MB import limit.",
            )
    try:
        summary = parse_deepseek_usage_export(
            bytes(archive),
            source_filename=filename,
        )
    except DeepSeekExportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    repository = AgentRunRepository(session)
    snapshot = repository.record_provider_billing_snapshot(
        ProviderBillingSnapshotCreate(
            provider="deepseek",
            period_start=summary.period_start,
            period_end=summary.period_end,
            currency=summary.currency,
            actual_cost=summary.actual_cost,
            total_tokens=summary.total_tokens,
            request_count=summary.request_count,
            source_reference=filename,
            metadata=summary.metadata,
            snapshot_key=f"provider:deepseek-export:{summary.content_sha256}",
        )
    )
    return _provider_billing_snapshot_response(snapshot)


@router.post(
    "/provider-account-snapshots",
    response_model=ProviderAccountSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_account_snapshot(
    payload: ProviderAccountSnapshotRequest,
    session: Session = Depends(get_db_session),
) -> ProviderAccountSnapshotResponse:
    """Store a point-in-time balance or Free Tier status, never a charge."""

    provider = payload.provider.strip().lower()
    normalized_source = (
        payload.source_reference.strip()
        if payload.source_reference and payload.source_reference.strip()
        else None
    )
    repository = AgentRunRepository(session)
    snapshot = repository.record_provider_account_snapshot(
        ProviderAccountSnapshotCreate(
            provider=provider,
            billing_tier=payload.billing_tier,
            billing_status=payload.billing_status.strip().lower(),
            currency=payload.currency,
            available_balance=payload.available_balance,
            paid_balance=payload.paid_balance,
            promotional_balance=payload.promotional_balance,
            source_reference=normalized_source,
            metadata=payload.metadata,
        )
    )
    return _provider_account_snapshot_response(snapshot)


@router.post(
    "/provider-account-snapshots/refresh",
    response_model=ProviderBalanceRefreshResponse,
)
def refresh_provider_account_snapshots(
    request: Request,
    session: Session = Depends(get_db_session),
) -> ProviderBalanceRefreshResponse:
    """Refresh supported balances without exposing provider credentials."""

    settings = request.app.state.settings
    if not settings.enable_cloud_services:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cloud services are disabled. Enable them before refreshing "
                "provider balances."
            ),
        )

    repository = AgentRunRepository(session)
    results: list[ProviderBalanceRefreshItemResponse] = []
    timeout_seconds = max(1.0, min(settings.tool_timeout_ms / 1000, 20.0))
    providers: tuple[
        tuple[str, str | None, Any],
        ...,
    ] = (
        (
            "deepseek",
            settings.deepseek_api_key,
            lambda: fetch_deepseek_balance(
                api_key=settings.deepseek_api_key or "",
                base_url=settings.deepseek_base_url,
                timeout_seconds=timeout_seconds,
            ),
        ),
        (
            "moonshot",
            settings.kimi_api_key,
            lambda: fetch_kimi_balance(
                api_key=settings.kimi_api_key or "",
                base_url=settings.kimi_base_url,
                timeout_seconds=timeout_seconds,
            ),
        ),
    )
    for provider, api_key, loader in providers:
        if not api_key:
            results.append(
                ProviderBalanceRefreshItemResponse(
                    provider=provider,
                    status="not_configured",
                    message="No API key is configured for this provider.",
                )
            )
            continue
        try:
            balance: ProviderBalance = loader()
            snapshot = repository.record_provider_account_snapshot(
                ProviderAccountSnapshotCreate(
                    provider=balance.provider,
                    # The balance endpoints do not disclose a subscription tier.
                    # Keep that field empty instead of inventing one.
                    billing_tier=None,
                    billing_status=balance.billing_status,
                    currency=balance.currency,
                    available_balance=balance.available_balance,
                    paid_balance=balance.paid_balance,
                    promotional_balance=balance.promotional_balance,
                    source_reference=balance.source_reference,
                    metadata=balance.metadata,
                )
            )
            results.append(
                ProviderBalanceRefreshItemResponse(
                    provider=provider,
                    status="updated",
                    message="Current balance and API availability were refreshed.",
                    snapshot=_provider_account_snapshot_response(snapshot),
                )
            )
        except ProviderBalanceError as exc:
            results.append(
                ProviderBalanceRefreshItemResponse(
                    provider=provider,
                    status="failed",
                    message=f"{exc.code}: {exc}",
                )
            )

    updated_count = sum(item.status == "updated" for item in results)
    return ProviderBalanceRefreshResponse(
        refreshed_at=datetime.now(timezone.utc),
        updated_count=updated_count,
        results=results,
    )


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: int,
    session: Session = Depends(get_db_session),
) -> RunDetailResponse:
    repository = AgentRunRepository(session)
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )
    model_calls = repository.list_model_calls(run_id=run_id)
    tool_calls = repository.list_tool_calls(run_id=run_id)
    ledger_queries = repository.list_evidence_ledger_queries(run_id=run_id)
    ledger_links = repository.list_evidence_ledger_links(run_id=run_id)
    call_counts = _call_counts(
        runs=[run],
        model_calls=model_calls,
        tool_calls=tool_calls,
    )
    return RunDetailResponse(
        run=_run_summary(run, call_counts=call_counts),
        model_calls=[_model_call_response(call) for call in model_calls],
        tool_calls=[_tool_call_response(call) for call in tool_calls],
        evidence_ledger_queries=[
            EvidenceLedgerQueryResponse(
                id=query.id,
                round_number=query.round_number,
                target_slot=query.target_slot,
                query=query.query_text,
                search_mode=query.search_mode,
                channel_counts=query.channel_counts_json,
                result_count=query.result_count,
            )
            for query in ledger_queries
        ],
        evidence_ledger_links=[
            EvidenceLedgerLinkResponse(
                query_id=link.query_id,
                chunk_id=link.chunk_id,
                evidence_item_id=link.evidence_item_id,
                accepted=link.accepted,
                fused_score=link.fused_score,
                match_signals=link.match_signals_json,
                channel_ranks=link.channel_ranks_json,
            )
            for link in ledger_links
        ],
        decision_trace=(
            run.metadata_json.get("decision_trace")
            if isinstance(run.metadata_json, dict)
            and isinstance(run.metadata_json.get("decision_trace"), dict)
            else None
        ),
    )


@dataclass(frozen=True)
class _CallCounts:
    model_calls_by_run: dict[int, int]
    tool_calls_by_run: dict[int, int]


def _call_counts(
    *,
    runs: list[AgentRun],
    model_calls: list[ModelCall],
    tool_calls: list[ToolCallRecord],
) -> _CallCounts:
    run_ids = {run.id for run in runs}
    model_counts: dict[int, int] = {run_id: 0 for run_id in run_ids}
    tool_counts: dict[int, int] = {run_id: 0 for run_id in run_ids}
    for model_call in model_calls:
        if model_call.run_id in model_counts:
            model_counts[model_call.run_id] += 1
    for tool_call in tool_calls:
        if tool_call.run_id in tool_counts:
            tool_counts[tool_call.run_id] += 1
    return _CallCounts(model_calls_by_run=model_counts, tool_calls_by_run=tool_counts)


def _run_summary(run: AgentRun, *, call_counts: _CallCounts) -> RunSummaryResponse:
    return RunSummaryResponse(
        id=run.id,
        run_key=run.run_key,
        role=run.role,
        objective=run.objective,
        status=run.status,
        sensitivity=run.sensitivity,
        as_of_date=run.as_of_date,
        selection_mode=run.selection_mode,
        selected_model=run.selected_model,
        selection_reason=run.selection_reason,
        total_tokens=run.total_tokens,
        total_estimated_cost_usd=float(run.total_estimated_cost_usd),
        model_call_count=call_counts.model_calls_by_run.get(run.id, 0),
        tool_call_count=call_counts.tool_calls_by_run.get(run.id, 0),
        created_at=run.created_at,
    )


def _model_breakdown(
    aggregates: list[ModelCallAggregate],
) -> list[ModelBreakdownResponse]:
    return [
        ModelBreakdownResponse(
            provider=row.provider,
            model=row.model,
            deployment=row.deployment,
            call_count=row.call_count,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            total_tokens=row.prompt_tokens + row.completion_tokens,
            total_estimated_cost_usd=row.total_estimated_cost_usd,
            avg_latency_ms=row.avg_latency_ms,
        )
        for row in aggregates
    ]


def _api_usage_breakdown(
    aggregates: list[ApiUsageAggregate],
) -> list[ModelBreakdownResponse]:
    return [
        ModelBreakdownResponse(
            provider=row.provider,
            model=row.model,
            deployment=row.deployment,
            call_count=row.call_count,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            total_tokens=row.prompt_tokens + row.completion_tokens,
            total_estimated_cost_usd=row.total_estimated_cost_usd,
            avg_latency_ms=None,
            input_cost_per_million_usd=row.input_cost_per_million_usd,
            output_cost_per_million_usd=row.output_cost_per_million_usd,
        )
        for row in aggregates
    ]


def _usage_summary(totals: UsageTotals) -> UsageSummaryResponse:
    return UsageSummaryResponse(
        call_count=totals.call_count,
        prompt_tokens=totals.prompt_tokens,
        completion_tokens=totals.completion_tokens,
        total_tokens=totals.prompt_tokens + totals.completion_tokens,
        total_estimated_cost_usd=totals.total_estimated_cost_usd,
        first_recorded_at=totals.first_recorded_at,
        last_recorded_at=totals.last_recorded_at,
    )


def _provider_billing_snapshot_response(
    snapshot: ProviderBillingSnapshot,
) -> ProviderBillingSnapshotResponse:
    return ProviderBillingSnapshotResponse(
        id=snapshot.id,
        provider=snapshot.provider,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        currency=snapshot.currency,
        actual_cost=float(snapshot.actual_cost),
        total_tokens=snapshot.total_tokens,
        request_count=snapshot.request_count,
        source_reference=snapshot.source_reference,
        metadata=snapshot.metadata_json,
        created_at=snapshot.created_at,
    )


def _provider_account_snapshot_response(
    snapshot: ProviderAccountSnapshot,
) -> ProviderAccountSnapshotResponse:
    return ProviderAccountSnapshotResponse(
        id=snapshot.id,
        provider=snapshot.provider,
        billing_tier=snapshot.billing_tier,
        billing_status=snapshot.billing_status,
        currency=snapshot.currency,
        available_balance=(
            float(snapshot.available_balance)
            if snapshot.available_balance is not None
            else None
        ),
        paid_balance=(
            float(snapshot.paid_balance) if snapshot.paid_balance is not None else None
        ),
        promotional_balance=(
            float(snapshot.promotional_balance)
            if snapshot.promotional_balance is not None
            else None
        ),
        source_reference=snapshot.source_reference,
        metadata=snapshot.metadata_json,
        created_at=snapshot.created_at,
    )


def _model_call_response(call: ModelCall) -> ModelCallResponse:
    return ModelCallResponse(
        id=call.id,
        provider=call.provider,
        model=call.model,
        deployment=call.deployment,
        serving_engine=call.serving_engine,
        prompt_tokens=call.prompt_tokens,
        completion_tokens=call.completion_tokens,
        total_tokens=call.prompt_tokens + call.completion_tokens,
        estimated_cost_usd=float(call.estimated_cost_usd),
        latency_ms=call.latency_ms,
        success=call.success,
        created_at=call.created_at,
    )


def _tool_call_response(call: ToolCallRecord) -> ToolCallResponse:
    return ToolCallResponse(
        id=call.id,
        call_id=call.call_id,
        tool_name=call.tool_name,
        status=call.status,
        arguments=call.arguments_json,
        output=call.output_json,
        error_code=call.error_code,
        latency_ms=call.latency_ms,
        created_at=call.created_at,
    )
