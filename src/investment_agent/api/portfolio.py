from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.api.style_packs import (
    resolve_method_documents,
    resolve_style_pack,
)
from investment_agent.method_documents import combined_method_context
from investment_agent.integrations.robinhood import (
    ProviderError,
    ProviderErrorCode,
)
from investment_agent.market_data import (
    MarketDataBatch,
    MarketDataSource,
    RobinhoodMarketDataSource,
    UploadedSnapshotMarketDataSource,
)
from investment_agent.portfolio import (
    AllocationSlice,
    CandidateQuote,
    CashGoal,
    CashPlan,
    ConcentrationFlag,
    CoverageGap,
    DcaSuggestion,
    FileUploadSource,
    HoldingRow,
    InvestmentCandidate,
    IndependentSearchMarketAnalysisService,
    MarketAnalysis,
    MarketAnalysisError,
    PortfolioSummary,
    RebalanceAction,
    RebalanceScenario,
    RecommendationContext,
    RetirementFundingPlan,
    RobinhoodMcpSource,
    ScenarioAllocation,
    ScenarioSuggestion,
    ScenarioTrade,
    summarize_portfolio,
    market_evidence_gate_query,
    market_prompt,
    market_search_query,
)
from investment_agent.portfolio.heatmap import (
    HeatmapSnapshot,
    HeatmapTile,
    build_heatmap_snapshot,
)
from investment_agent.providers import (
    GeminiModelProvider,
    OpenAICompatibleModelProvider,
)
from investment_agent.providers.types import ModelProvider
from investment_agent.repositories import (
    AgentRunCreate,
    AgentRunRepository,
    ModelCallCreate,
    PortfolioPositionCreate,
    PortfolioRepository,
    PortfolioSnapshotCreate,
    ToolCallRecordCreate,
    UserProfileRepository,
)
from investment_agent.storage import PortfolioPosition
from investment_agent.search import ExaSearchProvider

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
MAX_PORTFOLIO_UPLOAD_BYTES = 10 * 1024 * 1024


class PortfolioUploadRequest(BaseModel):
    path: str = Field(min_length=1)
    as_of_date: date | None = None


class MarketAnalysisRequest(BaseModel):
    requested_model: str = Field(min_length=1)


class MarketSourceResponse(BaseModel):
    citation_id: str
    title: str
    url: str
    retrieved_at: datetime


class MarketWatchlistCandidateResponse(BaseModel):
    symbol: str
    name: str
    category: str
    rationale: str
    counter_evidence: str
    invalidation_signal: str
    overlap_risk: str
    dca_guidance: str
    dca_suitable: bool
    dca_monthly_amount: float
    citation_ids: list[str]
    recommendation_mode: str


class MarketCandidateAuditResponse(BaseModel):
    index: int
    symbol: str | None
    requested_mode: str | None
    expected_mode: str | None
    supplied_citation_ids: list[str]
    accepted_citation_ids: list[str]
    present_fields: list[str]
    accepted: bool
    validation_codes: list[str]
    selection_source: str
    eligible: bool | None
    rank: int | None
    total_score: float | None
    score_components: dict[str, float]
    penalties: dict[str, float]
    market_signal_as_of: str | None


class MarketAnalysisResponse(BaseModel):
    run_id: int
    provider: str
    model: str
    generated_at: datetime
    content: str
    sources: list[MarketSourceResponse]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    source_method: str
    search_provider: str
    search_calls: int
    search_estimated_cost_usd: float
    answer_model_estimated_cost_usd: float
    answer_model_calls: int
    style_pack_id: str
    style_pack_name: str
    method_document_id: int | None
    method_document_name: str | None
    method_document_ids: list[int]
    method_document_names: list[str]
    source_count: int
    domain_count: int
    limitations: list[str]
    retrieved_result_count: int
    retrieved_domain_count: int
    gate_rejected_result_count: int
    watchlist: list[MarketWatchlistCandidateResponse]
    evidence_snapshot_id: str
    candidate_parse_status: str
    raw_candidate_count: int
    candidate_audit: list[MarketCandidateAuditResponse]
    selection_engine: str
    selection_version: str
    auditor_version: str
    audit_status: str
    audit_codes: list[str]


class PortfolioPositionResponse(BaseModel):
    symbol: str
    name: str
    asset_class: str
    quantity: float
    price: float
    market_value: float
    cost_basis: float | None
    account: str | None
    source_key: str
    source_scope: str
    as_of_date: date
    weight: float


class AllocationSliceResponse(BaseModel):
    asset_class: str
    market_value: float
    weight: float


class ConcentrationFlagResponse(BaseModel):
    code: str
    severity: str
    message: str
    symbol: str | None = None
    asset_class: str | None = None
    weight: float | None = None
    threshold: float | None = None
    excess_percentage_points: float | None = None


class ScenarioSuggestionResponse(BaseModel):
    scenario: str
    rationale: str


class InvestmentCandidateResponse(BaseModel):
    symbol: str
    name: str
    instrument_type: str
    asset_class: str
    portfolio_role: str
    rationale: str
    source_name: str
    source_url: str
    dca_eligible: bool
    satellite: bool
    candidate_category: str
    issuer: str
    exposure_key: str
    related_holdings: list[str]
    source_link_kind: str
    source_link_note: str
    source_checked_at: date | None


class RebalanceActionResponse(BaseModel):
    action: str
    asset_class: str
    symbol: str | None
    name: str | None
    amount: float
    estimated_shares: float | None
    reference_price: float | None
    price_as_of_date: date | None
    current_weight: float
    target_weight: float
    drift: float
    reference_kind: str
    reference_label: str
    rationale: str
    warnings: list[str]
    asset_description: str
    asset_url: str | None
    asset_source: str | None


class ScenarioAllocationResponse(BaseModel):
    asset_class: str
    market_value: float
    weight: float


class ScenarioTradeResponse(BaseModel):
    action: str
    asset_class: str
    symbol: str | None
    name: str | None
    amount: float
    estimated_shares: float | None
    reference_price: float | None
    price_as_of_date: date | None


class RebalanceScenarioResponse(BaseModel):
    code: str
    title: str
    description: str
    rebalancing_amount: float
    projected_total_value: float
    projected_allocation: list[ScenarioAllocationResponse]
    trades: list[ScenarioTradeResponse]
    limitations: list[str]


class CoverageGapResponse(BaseModel):
    asset_class: str
    current_weight: float
    target_weight: float | None
    gap_amount: float | None
    rationale: str
    candidates: list[InvestmentCandidateResponse]


class DcaSuggestionResponse(BaseModel):
    asset_class: str
    symbol: str | None
    name: str | None
    monthly_amount: float
    estimated_shares: float | None
    reference_price: float | None
    price_as_of_date: date | None
    rationale: str
    warnings: list[str]
    asset_description: str
    asset_url: str | None
    asset_source: str | None


class CashGoalResponse(BaseModel):
    code: str
    title: str
    target_amount: float
    allocated_current_savings: float
    remaining_gap: float
    months_remaining: int
    monthly_required: float
    deadline_label: str
    rationale: str
    priority: str
    funding_status: str


class CashPlanResponse(BaseModel):
    status: str
    as_of_date: date
    current_cash_savings: float
    total_target: float
    remaining_gap: float
    monthly_required: float
    monthly_net_income: float | None
    monthly_total_expenses: float | None
    monthly_investment: float
    monthly_capacity_for_cash_goals: float | None
    monthly_shortfall: float | None
    feasibility_status: str
    primary_financial_priority: str | None
    goals: list[CashGoalResponse]
    warnings: list[str]
    guidance: list[str]
    method: str


class RetirementFundingPlanResponse(BaseModel):
    status: str
    current_age: int | None
    retirement_age: int | None
    plan_through_age: int
    years_to_retirement: int | None
    retirement_years: int | None
    monthly_spending_today: float | None
    monthly_reliable_income_today: float
    monthly_reliable_income_after_tax: float | None
    monthly_spending_gap: float | None
    gross_monthly_portfolio_withdrawal: float | None
    current_invested_assets: float
    current_retirement_savings: float
    current_savings_source: str
    target_assets_at_retirement_today_dollars: float | None
    target_assets_at_retirement: float | None
    projected_current_assets_at_retirement: float | None
    required_monthly_investment: float | None
    estimated_monthly_take_home_cost: float | None
    planned_monthly_investment: float
    monthly_investment_gap: float | None
    inflation_rate: float
    annual_return: float
    real_annual_return: float
    accumulation_real_return: float
    retirement_real_return: float
    current_tax_rate: float | None
    retirement_tax_rate: float | None
    income_taxable: bool
    account_type: str | None
    taxable_withdrawal_share: float | None
    adjust_contributions_for_inflation: bool
    ending_balance_target: float
    warnings: list[str]
    guidance: list[str]
    method: str


class RecommendationContextResponse(BaseModel):
    status: str
    portfolio_as_of_date: date | None
    price_source: str
    generated_at: datetime
    live_market_data: bool
    analysis_method: str
    analysis_method_description: str
    policy: str
    disclaimer: str


class PortfolioSummaryResponse(BaseModel):
    total_value: float
    as_of_date: date | None
    positions: list[PortfolioPositionResponse]
    allocation: list[AllocationSliceResponse]
    concentration_flags: list[ConcentrationFlagResponse]
    scenarios: list[ScenarioSuggestionResponse]
    rebalance_actions: list[RebalanceActionResponse]
    rebalance_scenarios: list[RebalanceScenarioResponse]
    coverage_gaps: list[CoverageGapResponse]
    dca_suggestions: list[DcaSuggestionResponse]
    sector_candidates: list[InvestmentCandidateResponse]
    recommendation_context: RecommendationContextResponse
    cash_plan: CashPlanResponse
    retirement_plan: RetirementFundingPlanResponse


class PortfolioUploadResponse(BaseModel):
    import_id: str
    positions_count: int
    as_of_date: date
    as_of_date_source: str
    summary: PortfolioSummaryResponse


class HeatmapTileResponse(BaseModel):
    symbol: str
    name: str
    group: str
    exposure_key: str
    latest_price: float | None
    previous_close: float | None
    previous_close_date: date | None
    percent_change: float | None
    volume: float | None
    dollar_volume: float | None
    volume_z_score: float | None
    volume_activity: str
    volume_observation_date: date | None
    volume_reference_start: date | None
    volume_reference_end: date | None
    volume_reference_sessions: int
    volume_observation_value: float | None
    volume_reference_median: float | None
    volume_reference_log_mad: float | None
    volume_method: str
    volume_quality: str
    quote_observed_at: datetime | None
    quote_status: str
    directly_held: bool
    related_holdings: list[str]


class HeatmapResponse(BaseModel):
    provider_code: str
    provider_key: str
    provider_name: str
    configured_provider_code: str
    configured_provider_key: str
    configured_provider_name: str
    external_data_enabled: bool
    heatmap_enabled: bool
    unified_universe_enabled: bool
    is_live: bool
    is_delayed: bool
    status: str
    message: str
    generated_at: datetime
    tiles: list[HeatmapTileResponse]
    portfolio_summary: PortfolioSummaryResponse


@router.post(
    "/upload",
    response_model=PortfolioUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_portfolio(
    request: PortfolioUploadRequest,
    session: Session = Depends(get_db_session),
) -> PortfolioUploadResponse:
    path = Path(request.path)
    try:
        holdings = list(FileUploadSource(path=path).load().positions)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="Holdings CSV is not valid UTF-8 text.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _store_holdings(
        holdings,
        session=session,
        requested_as_of_date=request.as_of_date,
    )


@router.post(
    "/upload-file",
    response_model=PortfolioUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_portfolio_file(
    file: UploadFile = File(...),
    as_of_date: date | None = Form(default=None),
    session: Session = Depends(get_db_session),
) -> PortfolioUploadResponse:
    filename = Path(file.filename or "").name.strip()
    if not filename:
        raise HTTPException(status_code=422, detail="Uploaded file name is required.")

    raw_content = await file.read(MAX_PORTFOLIO_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw_content) > MAX_PORTFOLIO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Portfolio file exceeds the 10 MB upload limit.",
        )

    try:
        holdings = list(
            FileUploadSource(filename=filename, raw_content=raw_content).load().positions
        )
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="Holdings CSV is not valid UTF-8 text.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _store_holdings(
        holdings,
        session=session,
        requested_as_of_date=as_of_date,
    )


def _store_holdings(
    holdings: list[HoldingRow],
    *,
    session: Session,
    requested_as_of_date: date | None = None,
    date_source_override: str | None = None,
    source_key: str = "file_upload",
    source_name: str = "Uploaded portfolio file",
    source_scope: str = "manual",
    source_observed_at: datetime | None = None,
    source_is_live: bool = False,
) -> PortfolioUploadResponse:
    embedded_dates = {row.as_of_date for row in holdings if row.as_of_date is not None}
    embedded_date = next(iter(embedded_dates), None)
    if (
        requested_as_of_date is not None
        and embedded_date is not None
        and requested_as_of_date != embedded_date
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "The upload date does not match the spreadsheet as_of_date. "
                "Use one date for the whole snapshot."
            ),
        )
    snapshot_date = requested_as_of_date or embedded_date or date.today()
    if date_source_override is not None:
        date_source = date_source_override
    elif requested_as_of_date is not None:
        date_source = "upload_form"
    elif embedded_date is not None:
        date_source = "spreadsheet"
    else:
        date_source = "upload_date_fallback"

    import_id = f"portfolio-{uuid4().hex}"
    position_payloads = [
        PortfolioPositionCreate(
            symbol=row.symbol,
            name=row.name,
            asset_class=row.asset_class,
            quantity=row.quantity,
            price=row.price,
            market_value=row.market_value,
            cost_basis=row.cost_basis,
            account=row.account,
            import_id=import_id,
            as_of_date=snapshot_date,
            source_key=source_key,
            source_scope=source_scope,
        )
        for row in holdings
    ]
    repository = PortfolioRepository(session)
    records = repository.replace_source_positions(
        position_payloads,
        snapshot=PortfolioSnapshotCreate(
            snapshot_key=import_id,
            source_key=source_key,
            source_name=source_name,
            source_scope=source_scope,
            observed_at=source_observed_at or datetime.now(timezone.utc),
            is_live=source_is_live,
            metadata={"as_of_date_source": date_source},
        ),
    )
    merged_records = repository.list_positions()
    profile = UserProfileRepository(session).get_active_profile()
    summary = summarize_portfolio(merged_records, profile=profile)
    return PortfolioUploadResponse(
        import_id=import_id,
        positions_count=len(records),
        as_of_date=snapshot_date,
        as_of_date_source=date_source,
        summary=_summary_response(merged_records, summary),
    )


@router.get("/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    session: Session = Depends(get_db_session),
) -> PortfolioSummaryResponse:
    records = PortfolioRepository(session).list_positions()
    profile = UserProfileRepository(session).get_active_profile()
    summary = summarize_portfolio(records, profile=profile)
    return _summary_response(records, summary)


@router.post(
    "/sync-robinhood",
    response_model=PortfolioUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def sync_robinhood_portfolio(
    http_request: Request,
    session: Session = Depends(get_db_session),
) -> PortfolioUploadResponse:
    """Import a read-only Robinhood position snapshot through an injected MCP client."""

    settings = http_request.app.state.settings
    if not settings.enable_external_market_data:
        raise HTTPException(
            status_code=409,
            detail=(
                "External market and brokerage data is disabled. Set "
                "ARGUS_ENABLE_EXTERNAL_MARKET_DATA=true before connecting Robinhood."
            ),
        )
    if not settings.enable_robinhood:
        raise HTTPException(
            status_code=409,
            detail="Robinhood integration is disabled by ARGUS_ENABLE_ROBINHOOD.",
        )
    gateway = getattr(http_request.app.state, "robinhood_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Robinhood is not connected in this Argus session. Authenticate the "
                "read-only MCP connection before syncing positions."
            ),
        )
    try:
        snapshot = RobinhoodMcpSource(gateway).load()
    except ProviderError as exc:
        provider_status = {
            ProviderErrorCode.AUTH_REQUIRED: 401,
            ProviderErrorCode.AUTH_EXPIRED: 401,
            ProviderErrorCode.DENIED_TOOL: 403,
            ProviderErrorCode.CAPABILITY_DRIFT: 409,
            ProviderErrorCode.RATE_LIMITED: 429,
            ProviderErrorCode.PARTIAL_RESPONSE: 502,
            ProviderErrorCode.INVALID_RESPONSE: 502,
            ProviderErrorCode.TIMEOUT: 504,
        }.get(exc.code, 503)
        raise HTTPException(
            status_code=provider_status,
            detail=str(exc),
            headers={"X-Argus-Provider-Error": exc.code.value},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Robinhood did not return a usable read-only position snapshot.",
        ) from exc
    if not snapshot.positions:
        raise HTTPException(
            status_code=422,
            detail="Robinhood returned no supported equity positions.",
        )
    snapshot_date = max(
        row.as_of_date for row in snapshot.positions if row.as_of_date is not None
    )
    return _store_holdings(
        list(snapshot.positions),
        session=session,
        requested_as_of_date=snapshot_date,
        date_source_override="robinhood_mcp",
        source_key=snapshot.source_key,
        source_name=snapshot.source_name,
        source_scope=snapshot.source_scope,
        source_observed_at=snapshot.observed_at,
        source_is_live=snapshot.is_live,
    )


@router.get("/market-map", response_model=HeatmapResponse)
def get_portfolio_market_map(
    http_request: Request,
    refresh_historicals: bool = False,
    session: Session = Depends(get_db_session),
) -> HeatmapResponse:
    """Return the provider-neutral contract used by the future terminal heatmap."""

    settings = http_request.app.state.settings
    records = PortfolioRepository(session).list_positions()
    profile = UserProfileRepository(session).get_active_profile()
    summary = summarize_portfolio(records, profile=profile)
    unpriced_policy_symbols = {
        item.symbol
        for item in (*summary.rebalance_actions, *summary.dca_suggestions)
        if item.symbol is not None and item.reference_price is None
    }
    symbols = sorted(
        {candidate.symbol for candidate in summary.sector_candidates}
        | unpriced_policy_symbols
    )
    market_data = _resolve_market_data(
        http_request,
        positions=records,
        symbols=symbols,
        refresh_historicals=refresh_historicals,
    )
    candidate_quotes = {
        quote.symbol.upper(): CandidateQuote(
            symbol=quote.symbol.upper(),
            price=quote.last_price,
            as_of_date=(
                quote.observed_at.date()
                if quote.observed_at is not None
                else quote.previous_close_date
            ),
            source_name=market_data.provider_name,
            is_live=market_data.is_live,
        )
        for quote in market_data.quotes
        if quote.last_price is not None and quote.last_price > 0
    }
    summary = summarize_portfolio(
        records,
        profile=profile,
        candidate_quotes=candidate_quotes,
    )
    snapshot = build_heatmap_snapshot(
        candidates=summary.sector_candidates,
        positions=records,
        market_data=market_data,
        configured_provider_code=settings.market_data_provider_code,
        configured_provider_key=settings.market_data_provider_key,
        configured_provider_name=settings.market_data_provider_name,
        external_data_enabled=settings.enable_external_market_data,
    )
    return _heatmap_response(
        snapshot,
        heatmap_enabled=settings.enable_market_heatmap,
        unified_universe_enabled=settings.enable_unified_etf_universe,
        portfolio_summary=_summary_response(records, summary),
    )


def _resolve_market_data(
    http_request: Request,
    *,
    positions: list[PortfolioPosition],
    symbols: list[str],
    refresh_historicals: bool = False,
) -> MarketDataBatch:
    settings = http_request.app.state.settings
    fallback_source = UploadedSnapshotMarketDataSource(positions)
    if not settings.enable_external_market_data:
        return replace(
            fallback_source.fetch_quotes(symbols),
            status="external_disabled",
            message=(
                "External market data is off. Prices, when available, come from the "
                "uploaded portfolio snapshot and are explicitly Not live."
            ),
        )

    source: MarketDataSource | None = getattr(
        http_request.app.state,
        "market_data_source",
        None,
    )
    if settings.market_data_provider_code == "01":
        if not settings.enable_robinhood:
            return replace(
                fallback_source.fetch_quotes(symbols),
                status="robinhood_disabled",
                message=(
                    "Robinhood is the configured provider but its integration is off. "
                    "Uploaded prices are shown as Not live."
                ),
            )
        if source is None:
            gateway = getattr(http_request.app.state, "robinhood_gateway", None)
            if gateway is not None:
                source = RobinhoodMarketDataSource(
                    gateway,
                    cache_store=http_request.app.state.cache_store,
                    enable_historicals=settings.robinhood_enable_historicals,
                )
    if source is None:
        return replace(
            fallback_source.fetch_quotes(symbols),
            status="connection_required",
            message=(
                f"{settings.market_data_provider_name} is configured but not connected. "
                "Uploaded prices are shown as Not live."
            ),
        )
    if source.provider_code != settings.market_data_provider_code:
        return replace(
            fallback_source.fetch_quotes(symbols),
            status="provider_mismatch",
            message=(
                "The connected market-data adapter does not match the explicitly "
                "configured provider. Argus did not switch providers; uploaded prices "
                "are shown as Not live."
            ),
        )
    try:
        if isinstance(source, RobinhoodMarketDataSource):
            return source.fetch_quotes(
                symbols,
                refresh_historicals=refresh_historicals,
            )
        return source.fetch_quotes(symbols)
    except Exception:
        return replace(
            fallback_source.fetch_quotes(symbols),
            status="provider_error",
            message=(
                f"{settings.market_data_provider_name} could not return quotes. Argus "
                "did not switch to another external provider; uploaded prices are shown "
                "as Not live."
            ),
        )


def _heatmap_response(
    snapshot: HeatmapSnapshot,
    *,
    heatmap_enabled: bool,
    unified_universe_enabled: bool,
    portfolio_summary: PortfolioSummaryResponse,
) -> HeatmapResponse:
    return HeatmapResponse(
        provider_code=snapshot.provider_code,
        provider_key=snapshot.provider_key,
        provider_name=snapshot.provider_name,
        configured_provider_code=snapshot.configured_provider_code,
        configured_provider_key=snapshot.configured_provider_key,
        configured_provider_name=snapshot.configured_provider_name,
        external_data_enabled=snapshot.external_data_enabled,
        heatmap_enabled=heatmap_enabled,
        unified_universe_enabled=unified_universe_enabled,
        is_live=snapshot.is_live,
        is_delayed=snapshot.is_delayed,
        status=snapshot.status,
        message=snapshot.message,
        generated_at=snapshot.generated_at,
        tiles=[_heatmap_tile_response(tile) for tile in snapshot.tiles],
        portfolio_summary=portfolio_summary,
    )


def _heatmap_tile_response(tile: HeatmapTile) -> HeatmapTileResponse:
    return HeatmapTileResponse(
        symbol=tile.symbol,
        name=tile.name,
        group=tile.group,
        exposure_key=tile.exposure_key,
        latest_price=tile.latest_price,
        previous_close=tile.previous_close,
        previous_close_date=tile.previous_close_date,
        percent_change=tile.percent_change,
        volume=tile.volume,
        dollar_volume=tile.dollar_volume,
        volume_z_score=tile.volume_z_score,
        volume_activity=tile.volume_activity,
        volume_observation_date=tile.volume_observation_date,
        volume_reference_start=tile.volume_reference_start,
        volume_reference_end=tile.volume_reference_end,
        volume_reference_sessions=tile.volume_reference_sessions,
        volume_observation_value=tile.volume_observation_value,
        volume_reference_median=tile.volume_reference_median,
        volume_reference_log_mad=tile.volume_reference_log_mad,
        volume_method=tile.volume_method,
        volume_quality=tile.volume_quality,
        quote_observed_at=tile.quote_observed_at,
        quote_status=tile.quote_status,
        directly_held=tile.directly_held,
        related_holdings=list(tile.related_holdings),
    )


@router.post("/market-analysis", response_model=MarketAnalysisResponse)
def create_market_analysis(
    payload: MarketAnalysisRequest,
    http_request: Request,
    session: Session = Depends(get_db_session),
) -> MarketAnalysisResponse:
    settings = http_request.app.state.settings
    records = PortfolioRepository(session).list_positions()
    if not records:
        raise HTTPException(status_code=422, detail="Upload a portfolio first.")

    if not (settings.enable_cloud_services and settings.exa_api_key):
        raise HTTPException(
            status_code=422,
            detail=(
                "Portfolio market analysis requires cloud services and an Exa API key. "
                "Exa retrieves cited evidence independently from the selected answer model."
            ),
        )
    answer_provider = _market_answer_provider(settings, payload.requested_model)
    search_provider = ExaSearchProvider(
        api_key=settings.exa_api_key,
        base_url=settings.exa_base_url,
        search_type=settings.exa_search_type,
        timeout_ms=settings.exa_timeout_ms,
        max_results=settings.exa_max_results,
        highlight_max_characters=settings.exa_highlight_max_characters,
        search_cost_per_request=settings.exa_search_cost_per_request,
    )
    snapshot_date = max(record.as_of_date for record in records)
    profile = UserProfileRepository(session).get_active_profile()
    style_pack = resolve_style_pack(
        session,
        profile.preferred_style if profile is not None else None,
    )
    method_document_ids = (
        list(profile.preferred_method_document_ids_json or [])
        if profile is not None
        else []
    )
    if (
        not method_document_ids
        and profile is not None
        and profile.preferred_method_document_id is not None
    ):
        method_document_ids = [profile.preferred_method_document_id]
    method_documents = resolve_method_documents(session, method_document_ids)
    summary = summarize_portfolio(records, profile=profile)
    run_repository = AgentRunRepository(session)
    run_record = run_repository.create_run(
        AgentRunCreate(
            run_key=f"portfolio-market-{uuid4().hex}",
            role="portfolio_market_analysis",
            objective="Generate cited Portfolio market context and validate ETF candidates.",
            status="running",
            sensitivity="internal",
            as_of_date=snapshot_date,
            selection_mode="manual",
            selected_model=payload.requested_model,
            selection_reason=(
                "The user explicitly selected the only answer model. Exa searches "
                f"independently; ETF selection engine={settings.etf_selection_engine}. "
                "Argus never switches either boundary silently."
            ),
            metadata={
                "trace_type": "portfolio_market_analysis",
                "trace_schema_version": "2.0",
                "selection_engine": settings.etf_selection_engine,
                "privacy": {
                    "raw_prompt_stored": False,
                    "raw_model_response_stored": False,
                    "full_web_pages_stored": False,
                    "account_names_stored": False,
                    "holding_dollar_values_stored": False,
                    "api_keys_stored": False,
                },
            },
        )
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=search_provider,
        answer_provider=answer_provider,
        max_search_calls=settings.web_search_max_calls,
        research_candidates=list(summary.sector_candidates),
        positions=records,
        profile=profile,
        selection_engine=settings.etf_selection_engine,
    )
    started_at = perf_counter()
    try:
        analysis = service.analyze(
            market_prompt(
                records,
                portfolio_as_of=snapshot_date.isoformat(),
                policy_actions=summary.rebalance_actions,
                research_candidates=summary.sector_candidates,
                style_context=combined_method_context(style_pack, method_documents),
                profile=profile,
                selection_engine=settings.etf_selection_engine,
            ),
            search_query=market_search_query(records),
            evidence_gate_query=market_evidence_gate_query(),
        )
    except MarketAnalysisError as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        _persist_market_analysis_failure(
            run_repository,
            run_id=run_record.id,
            requested_model=payload.requested_model,
            answer_provider=answer_provider,
            error=exc,
            elapsed_ms=elapsed_ms,
            retention_count=settings.market_analysis_trace_retention_count,
            retention_days=settings.market_analysis_trace_retention_days,
            selection_engine=settings.etf_selection_engine,
        )
        # Error responses normally roll back the request-scoped session. Commit the
        # bounded failure trace first so provider/search failures remain auditable.
        session.commit()
        status_code = (
            429
            if exc.code
            in {
                "provider_quota_exhausted",
                "provider_balance_exhausted",
                "provider_overloaded",
                "provider_rate_limited",
                "web_search_rate_limited",
            }
            else 502
        )
        provider_name = _market_provider_display_name(payload.requested_model)
        messages: dict[str, str] = {
            "provider_authentication_failed": (
                f"{provider_name} rejected the API key or its permissions. Check the "
                "matching ARGUS_*_API_KEY in the project-root .env file, then restart "
                "Docker Compose."
            ),
            "web_search_authentication_failed": (
                "Exa rejected ARGUS_EXA_API_KEY or its permissions. Update the "
                "project-root .env file and restart Docker Compose; Argus did not "
                "call the selected answer model."
            ),
            "web_search_rate_limited": (
                "Exa rate-limited the search request. Wait for the Exa retry window "
                "before trying again; Argus did not call or switch answer models."
            ),
        }
        if provider_name == "Gemini":
            messages["provider_quota_exhausted"] = (
                "Gemini returned HTTP 429. A short-window limit may clear within "
                "minutes; Free Tier daily request quotas normally reset at midnight "
                "Pacific Time. Argus did not enable billing or produce an analysis."
            )
        elif provider_name == "Kimi":
            messages.update(
                {
                    "provider_balance_exhausted": (
                        "Kimi accepted the API key, but the account has no available "
                        "cash or voucher balance. Add funds in the Kimi API platform "
                        "before retrying. No analysis or Argus cost was produced."
                    ),
                    "provider_rate_limited": (
                        "Kimi accepted the API key, but this request exceeded the "
                        "account RPM, TPM, daily-token, or concurrency limit. Wait for "
                        "the provider-specified retry window before trying again."
                    ),
                    "provider_overloaded": (
                        "Kimi is temporarily overloaded. Try again later; no analysis "
                        "or Argus cost was produced."
                    ),
                    "provider_quota_exhausted": (
                        "Kimi returned HTTP 429. Check the Kimi API platform balance, "
                        "project budget, and rate-limit dashboard before retrying."
                    ),
                }
            )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": messages.get(exc.code, str(exc))},
        ) from exc
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    _persist_market_analysis_success(
        run_repository,
        run_id=run_record.id,
        analysis=analysis,
        requested_model=payload.requested_model,
        answer_provider=answer_provider,
        portfolio_as_of=snapshot_date,
        position_count=len(records),
        profile_present=profile is not None,
        elapsed_ms=elapsed_ms,
        retention_count=settings.market_analysis_trace_retention_count,
        retention_days=settings.market_analysis_trace_retention_days,
    )
    return _market_analysis_response(
        analysis,
        run_id=run_record.id,
        style_pack=style_pack,
        method_documents=method_documents,
        profile=profile,
    )


def _market_answer_provider(settings, requested_model: str) -> ModelProvider:
    common = {
        "timeout_ms": settings.market_analysis_timeout_ms,
        "max_attempts": settings.market_analysis_max_attempts,
        "retry_backoff_ms": settings.model_retry_backoff_ms,
        "max_tokens": settings.market_analysis_max_output_tokens,
    }
    if (
        requested_model == f"google/{settings.gemini_model}"
        and settings.enable_cloud_services
        and settings.gemini_api_key
    ):
        return GeminiModelProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            input_cost_per_million=settings.gemini_input_cost_per_million,
            output_cost_per_million=settings.gemini_output_cost_per_million,
            **common,
        )
    if (
        requested_model == f"deepseek/{settings.deepseek_model}"
        and settings.enable_cloud_services
        and settings.deepseek_api_key
    ):
        return OpenAICompatibleModelProvider(
            provider_name="deepseek",
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            serving_engine="deepseek-api",
            input_cost_per_million=settings.deepseek_input_cost_per_million,
            output_cost_per_million=settings.deepseek_output_cost_per_million,
            **common,
        )
    if (
        requested_model == f"moonshot/{settings.kimi_model}"
        and settings.enable_cloud_services
        and settings.kimi_api_key
    ):
        return OpenAICompatibleModelProvider(
            provider_name="moonshot",
            api_key=settings.kimi_api_key,
            model=settings.kimi_model,
            base_url=settings.kimi_base_url,
            serving_engine="moonshot-api",
            input_cost_per_million=settings.kimi_input_cost_per_million,
            output_cost_per_million=settings.kimi_output_cost_per_million,
            **common,
        )
    raise HTTPException(
        status_code=422,
        detail=(
            "Choose a configured Gemini, DeepSeek, or Kimi answer model. Argus will "
            "use only that model after Exa retrieves accepted evidence."
        ),
    )


def _market_provider_display_name(requested_model: str) -> str:
    if requested_model.startswith("google/"):
        return "Gemini"
    if requested_model.startswith("deepseek/"):
        return "DeepSeek"
    return "Kimi"


def _summary_response(
    records: list[PortfolioPosition],
    summary: PortfolioSummary,
) -> PortfolioSummaryResponse:
    sorted_records = sorted(
        records, key=lambda record: record.market_value, reverse=True
    )
    return PortfolioSummaryResponse(
        total_value=summary.total_value,
        as_of_date=summary.recommendation_context.portfolio_as_of_date,
        positions=[
            PortfolioPositionResponse(
                symbol=record.symbol,
                name=record.name,
                asset_class=position_summary.asset_class,
                quantity=record.quantity,
                price=record.price,
                market_value=record.market_value,
                cost_basis=record.cost_basis,
                account=record.account,
                source_key=record.source_key,
                source_scope=record.source_scope,
                as_of_date=record.as_of_date,
                weight=(
                    record.market_value / summary.total_value
                    if summary.total_value > 0
                    else 0.0
                ),
            )
            for record, position_summary in zip(
                sorted_records,
                summary.positions,
                strict=True,
            )
        ],
        allocation=[
            _allocation_response(allocation_slice)
            for allocation_slice in summary.allocation
        ],
        concentration_flags=[
            _flag_response(flag) for flag in summary.concentration_flags
        ],
        scenarios=[_scenario_response(scenario) for scenario in summary.scenarios],
        rebalance_actions=[
            _rebalance_action_response(action) for action in summary.rebalance_actions
        ],
        rebalance_scenarios=[
            _rebalance_scenario_response(scenario)
            for scenario in summary.rebalance_scenarios
        ],
        coverage_gaps=[_coverage_gap_response(gap) for gap in summary.coverage_gaps],
        dca_suggestions=[
            _dca_suggestion_response(suggestion)
            for suggestion in summary.dca_suggestions
        ],
        sector_candidates=[
            _candidate_response(candidate) for candidate in summary.sector_candidates
        ],
        recommendation_context=_recommendation_context_response(
            summary.recommendation_context
        ),
        cash_plan=_cash_plan_response(summary.cash_plan),
        retirement_plan=_retirement_plan_response(summary.retirement_plan),
    )


def _allocation_response(
    allocation_slice: AllocationSlice,
) -> AllocationSliceResponse:
    return AllocationSliceResponse(
        asset_class=allocation_slice.asset_class,
        market_value=allocation_slice.market_value,
        weight=allocation_slice.weight,
    )


def _flag_response(flag: ConcentrationFlag) -> ConcentrationFlagResponse:
    return ConcentrationFlagResponse(
        code=flag.code,
        severity=flag.severity,
        message=flag.message,
        symbol=flag.symbol,
        asset_class=flag.asset_class,
        weight=flag.weight,
        threshold=flag.threshold,
        excess_percentage_points=flag.excess_percentage_points,
    )


def _scenario_response(
    scenario: ScenarioSuggestion,
) -> ScenarioSuggestionResponse:
    return ScenarioSuggestionResponse(
        scenario=scenario.scenario,
        rationale=scenario.rationale,
    )


def _candidate_response(candidate: InvestmentCandidate) -> InvestmentCandidateResponse:
    return InvestmentCandidateResponse(
        symbol=candidate.symbol,
        name=candidate.name,
        instrument_type=candidate.instrument_type,
        asset_class=candidate.asset_class,
        portfolio_role=candidate.portfolio_role,
        rationale=candidate.rationale,
        source_name=candidate.source_name,
        source_url=candidate.source_url,
        dca_eligible=candidate.dca_eligible,
        satellite=candidate.satellite,
        candidate_category=candidate.candidate_category,
        issuer=candidate.issuer,
        exposure_key=candidate.exposure_key,
        related_holdings=list(candidate.related_holdings),
        source_link_kind=candidate.source_link_kind,
        source_link_note=candidate.source_link_note,
        source_checked_at=candidate.source_checked_at,
    )


def _rebalance_action_response(action: RebalanceAction) -> RebalanceActionResponse:
    return RebalanceActionResponse(
        action=action.action,
        asset_class=action.asset_class,
        symbol=action.symbol,
        name=action.name,
        amount=action.amount,
        estimated_shares=action.estimated_shares,
        reference_price=action.reference_price,
        price_as_of_date=action.price_as_of_date,
        current_weight=action.current_weight,
        target_weight=action.target_weight,
        drift=action.drift,
        reference_kind=action.reference_kind,
        reference_label=action.reference_label,
        rationale=action.rationale,
        warnings=list(action.warnings),
        asset_description=action.asset_description,
        asset_url=action.asset_url,
        asset_source=action.asset_source,
    )


def _scenario_allocation_response(
    allocation: ScenarioAllocation,
) -> ScenarioAllocationResponse:
    return ScenarioAllocationResponse(
        asset_class=allocation.asset_class,
        market_value=allocation.market_value,
        weight=allocation.weight,
    )


def _scenario_trade_response(trade: ScenarioTrade) -> ScenarioTradeResponse:
    return ScenarioTradeResponse(
        action=trade.action,
        asset_class=trade.asset_class,
        symbol=trade.symbol,
        name=trade.name,
        amount=trade.amount,
        estimated_shares=trade.estimated_shares,
        reference_price=trade.reference_price,
        price_as_of_date=trade.price_as_of_date,
    )


def _rebalance_scenario_response(
    scenario: RebalanceScenario,
) -> RebalanceScenarioResponse:
    return RebalanceScenarioResponse(
        code=scenario.code,
        title=scenario.title,
        description=scenario.description,
        rebalancing_amount=scenario.rebalancing_amount,
        projected_total_value=scenario.projected_total_value,
        projected_allocation=[
            _scenario_allocation_response(allocation)
            for allocation in scenario.projected_allocation
        ],
        trades=[_scenario_trade_response(trade) for trade in scenario.trades],
        limitations=list(scenario.limitations),
    )


def _coverage_gap_response(gap: CoverageGap) -> CoverageGapResponse:
    return CoverageGapResponse(
        asset_class=gap.asset_class,
        current_weight=gap.current_weight,
        target_weight=gap.target_weight,
        gap_amount=gap.gap_amount,
        rationale=gap.rationale,
        candidates=[_candidate_response(candidate) for candidate in gap.candidates],
    )


def _dca_suggestion_response(suggestion: DcaSuggestion) -> DcaSuggestionResponse:
    return DcaSuggestionResponse(
        asset_class=suggestion.asset_class,
        symbol=suggestion.symbol,
        name=suggestion.name,
        monthly_amount=suggestion.monthly_amount,
        estimated_shares=suggestion.estimated_shares,
        reference_price=suggestion.reference_price,
        price_as_of_date=suggestion.price_as_of_date,
        rationale=suggestion.rationale,
        warnings=list(suggestion.warnings),
        asset_description=suggestion.asset_description,
        asset_url=suggestion.asset_url,
        asset_source=suggestion.asset_source,
    )


def _cash_goal_response(goal: CashGoal) -> CashGoalResponse:
    return CashGoalResponse(
        code=goal.code,
        title=goal.title,
        target_amount=goal.target_amount,
        allocated_current_savings=goal.allocated_current_savings,
        remaining_gap=goal.remaining_gap,
        months_remaining=goal.months_remaining,
        monthly_required=goal.monthly_required,
        deadline_label=goal.deadline_label,
        rationale=goal.rationale,
        priority=goal.priority,
        funding_status=goal.funding_status,
    )


def _cash_plan_response(plan: CashPlan) -> CashPlanResponse:
    return CashPlanResponse(
        status=plan.status,
        as_of_date=plan.as_of_date,
        current_cash_savings=plan.current_cash_savings,
        total_target=plan.total_target,
        remaining_gap=plan.remaining_gap,
        monthly_required=plan.monthly_required,
        monthly_net_income=plan.monthly_net_income,
        monthly_total_expenses=plan.monthly_total_expenses,
        monthly_investment=plan.monthly_investment,
        monthly_capacity_for_cash_goals=plan.monthly_capacity_for_cash_goals,
        monthly_shortfall=plan.monthly_shortfall,
        feasibility_status=plan.feasibility_status,
        primary_financial_priority=plan.primary_financial_priority,
        goals=[_cash_goal_response(goal) for goal in plan.goals],
        warnings=list(plan.warnings),
        guidance=list(plan.guidance),
        method=plan.method,
    )


def _retirement_plan_response(
    plan: RetirementFundingPlan,
) -> RetirementFundingPlanResponse:
    return RetirementFundingPlanResponse(
        status=plan.status,
        current_age=plan.current_age,
        retirement_age=plan.retirement_age,
        plan_through_age=plan.plan_through_age,
        years_to_retirement=plan.years_to_retirement,
        retirement_years=plan.retirement_years,
        monthly_spending_today=plan.monthly_spending_today,
        monthly_reliable_income_today=plan.monthly_reliable_income_today,
        monthly_reliable_income_after_tax=plan.monthly_reliable_income_after_tax,
        monthly_spending_gap=plan.monthly_spending_gap,
        gross_monthly_portfolio_withdrawal=plan.gross_monthly_portfolio_withdrawal,
        current_invested_assets=plan.current_invested_assets,
        current_retirement_savings=plan.current_retirement_savings,
        current_savings_source=plan.current_savings_source,
        target_assets_at_retirement_today_dollars=(
            plan.target_assets_at_retirement_today_dollars
        ),
        target_assets_at_retirement=plan.target_assets_at_retirement,
        projected_current_assets_at_retirement=(
            plan.projected_current_assets_at_retirement
        ),
        required_monthly_investment=plan.required_monthly_investment,
        estimated_monthly_take_home_cost=plan.estimated_monthly_take_home_cost,
        planned_monthly_investment=plan.planned_monthly_investment,
        monthly_investment_gap=plan.monthly_investment_gap,
        inflation_rate=plan.inflation_rate,
        annual_return=plan.annual_return,
        real_annual_return=plan.real_annual_return,
        accumulation_real_return=plan.accumulation_real_return,
        retirement_real_return=plan.retirement_real_return,
        current_tax_rate=plan.current_tax_rate,
        retirement_tax_rate=plan.retirement_tax_rate,
        income_taxable=plan.income_taxable,
        account_type=plan.account_type,
        taxable_withdrawal_share=plan.taxable_withdrawal_share,
        adjust_contributions_for_inflation=(plan.adjust_contributions_for_inflation),
        ending_balance_target=plan.ending_balance_target,
        warnings=list(plan.warnings),
        guidance=list(plan.guidance),
        method=plan.method,
    )


def _persist_market_analysis_success(
    repository: AgentRunRepository,
    *,
    run_id: int,
    analysis: MarketAnalysis,
    requested_model: str,
    answer_provider: ModelProvider,
    portfolio_as_of: date,
    position_count: int,
    profile_present: bool,
    elapsed_ms: int,
    retention_count: int,
    retention_days: int,
) -> None:
    audit_rows = [
        {
            "index": item.index,
            "symbol": item.symbol,
            "requested_mode": item.requested_mode,
            "expected_mode": item.expected_mode,
            "supplied_citation_ids": list(item.supplied_citation_ids),
            "accepted_citation_ids": list(item.accepted_citation_ids),
            "present_fields": list(item.present_fields),
            "accepted": item.accepted,
            "validation_codes": list(item.validation_codes),
            "selection_source": getattr(item, "selection_source", "model"),
            "eligible": getattr(item, "eligible", None),
            "rank": getattr(item, "rank", None),
            "total_score": getattr(item, "total_score", None),
            "score_components": dict(getattr(item, "score_components", ())),
            "penalties": dict(getattr(item, "penalties", ())),
            "market_signal_as_of": getattr(item, "market_signal_as_of", None),
        }
        for item in getattr(analysis, "candidate_audit", ())
    ]
    accepted_symbols = [str(item.symbol) for item in getattr(analysis, "watchlist", ())]
    source_domains = sorted(
        {
            domain
            for source in analysis.sources
            if (domain := _safe_source_domain(source.url))
        }
    )
    decision_trace = {
        "schema_version": "2.0",
        "status": "complete",
        "selection_engine": getattr(analysis, "selection_engine", "model"),
        "selection_version": getattr(
            analysis, "selection_version", "selected-model-watchlist-v1"
        ),
        "auditor_version": getattr(
            analysis, "auditor_version", "model-output-validator-v1"
        ),
        "audit_status": getattr(analysis, "audit_status", "passed"),
        "audit_codes": list(getattr(analysis, "audit_codes", ())),
        "selection_engine_limitation": (
            "Legacy rollback mode: the selected model proposes candidates without "
            "the deterministic score threshold. Controlled-universe, citation, and "
            "holdings-mode safety validation still applies."
            if getattr(analysis, "selection_engine", "model") == "model"
            else None
        ),
        "prompt_version": "portfolio-market-watchlist-v2",
        "evidence_snapshot_id": getattr(analysis, "evidence_snapshot_id", ""),
        "evidence_as_of": analysis.generated_at.isoformat(),
        "accepted_citation_ids": [source.citation_id for source in analysis.sources],
        "accepted_source_domains": source_domains,
        "candidate_parse_status": getattr(
            analysis,
            "candidate_parse_status",
            "not_available",
        ),
        "raw_candidate_count": getattr(analysis, "raw_candidate_count", 0),
        "accepted_candidate_symbols": accepted_symbols,
        "accepted_candidate_count": len(accepted_symbols),
        "rejected_candidate_count": sum(
            1 for item in audit_rows if not item["accepted"]
        ),
        "candidate_outcomes": audit_rows,
        "portfolio_input_summary": {
            "portfolio_as_of": portfolio_as_of.isoformat(),
            "position_count": position_count,
            "profile_present": profile_present,
        },
        "privacy": {
            "raw_prompt_stored": False,
            "raw_model_response_stored": False,
            "full_web_pages_stored": False,
            "account_names_stored": False,
            "holding_dollar_values_stored": False,
            "api_keys_stored": False,
        },
        "retention": {
            "role_limit": retention_count,
            "max_age_days": retention_days,
            "cache_used": False,
        },
    }
    repository.record_tool_call(
        ToolCallRecordCreate(
            run_id=run_id,
            call_id=f"exa-market-{uuid4().hex[:12]}",
            tool_name="exa_market_search_and_evidence_gate",
            status="ok",
            arguments={
                "facets": ["portfolio_drivers", "sector_outlook"],
                "maximum_search_calls": analysis.search_calls,
                "stores_full_pages": False,
            },
            output={
                "evidence_snapshot_id": getattr(
                    analysis,
                    "evidence_snapshot_id",
                    "",
                ),
                "retrieved_result_count": getattr(
                    analysis, "retrieved_result_count", 0
                ),
                "retrieved_domain_count": getattr(
                    analysis, "retrieved_domain_count", 0
                ),
                "accepted_source_count": getattr(
                    analysis, "source_count", len(analysis.sources)
                ),
                "accepted_domain_count": getattr(
                    analysis, "domain_count", len(source_domains)
                ),
                "gate_rejected_result_count": getattr(
                    analysis, "gate_rejected_result_count", 0
                ),
                "accepted_citation_ids": [
                    source.citation_id for source in analysis.sources
                ],
            },
        )
    )
    repository.record_model_call(
        ModelCallCreate(
            run_id=run_id,
            provider=analysis.provider,
            model=analysis.model,
            deployment=_provider_deployment(answer_provider),
            serving_engine=getattr(answer_provider, "serving_engine", None),
            prompt_tokens=analysis.prompt_tokens,
            completion_tokens=analysis.completion_tokens,
            estimated_cost_usd=analysis.answer_model_estimated_cost_usd,
            success=True,
            request_count=max(1, getattr(analysis, "answer_model_calls", 1)),
            input_cost_per_million_usd=getattr(
                answer_provider, "input_cost_per_million_usd", None
            ),
            output_cost_per_million_usd=getattr(
                answer_provider, "output_cost_per_million_usd", None
            ),
        )
    )
    repository.update_run(
        run_id,
        status="complete",
        total_tokens=analysis.prompt_tokens + analysis.completion_tokens,
        total_estimated_cost_usd=analysis.estimated_cost_usd,
        selection_reason=(
            f"Manual model {requested_model}; Exa supplied a bounded evidence "
            f"snapshot; ETF selection engine={getattr(analysis, 'selection_engine', 'model')} "
            "before the selected model synthesized the explanation."
        ),
        metadata={
            "trace_type": "portfolio_market_analysis",
            "trace_schema_version": "2.0",
            "elapsed_ms": elapsed_ms,
            "decision_trace": decision_trace,
        },
    )
    repository.prune_runs_by_role(
        role="portfolio_market_analysis",
        keep_latest=retention_count,
        max_age_days=retention_days,
    )


def _persist_market_analysis_failure(
    repository: AgentRunRepository,
    *,
    run_id: int,
    requested_model: str,
    answer_provider: ModelProvider,
    error: MarketAnalysisError,
    elapsed_ms: int,
    retention_count: int,
    retention_days: int,
    selection_engine: str = "deterministic",
) -> None:
    search_failed = error.code.startswith("web_search_")
    repository.record_tool_call(
        ToolCallRecordCreate(
            run_id=run_id,
            call_id=f"exa-market-{uuid4().hex[:12]}",
            tool_name="exa_market_search_and_evidence_gate",
            status="failed" if search_failed else "unknown",
            arguments={
                "facets": ["portfolio_drivers", "sector_outlook"],
                "stores_full_pages": False,
            },
            output={"bounded_failure_trace": True},
            error_code=error.code if search_failed else None,
        )
    )
    if error.prompt_tokens or error.completion_tokens:
        repository.record_model_call(
            ModelCallCreate(
                run_id=run_id,
                provider=getattr(answer_provider, "provider_name", "unknown"),
                model=getattr(answer_provider, "model_name", requested_model),
                deployment=_provider_deployment(answer_provider),
                serving_engine=getattr(answer_provider, "serving_engine", None),
                prompt_tokens=error.prompt_tokens,
                completion_tokens=error.completion_tokens,
                # Error cost can include Exa, so keep the complete estimate on
                # AgentRun rather than misattributing it to the model-call row.
                estimated_cost_usd=0.0,
                success=False,
                input_cost_per_million_usd=getattr(
                    answer_provider, "input_cost_per_million_usd", None
                ),
                output_cost_per_million_usd=getattr(
                    answer_provider, "output_cost_per_million_usd", None
                ),
            )
        )
    repository.update_run(
        run_id,
        status="failed",
        total_tokens=error.prompt_tokens + error.completion_tokens,
        total_estimated_cost_usd=error.estimated_cost_usd,
        metadata={
            "trace_type": "portfolio_market_analysis",
            "trace_schema_version": "2.0",
            "elapsed_ms": elapsed_ms,
            "decision_trace": {
                "schema_version": "2.0",
                "status": "failed",
                "failure_code": error.code,
                "selection_engine": selection_engine,
                "candidate_parse_status": "not_reached",
                "candidate_outcomes": [],
                "privacy": {
                    "raw_prompt_stored": False,
                    "raw_model_response_stored": False,
                    "full_web_pages_stored": False,
                    "account_names_stored": False,
                    "holding_dollar_values_stored": False,
                    "api_keys_stored": False,
                },
                "retention": {
                    "role_limit": retention_count,
                    "max_age_days": retention_days,
                    "cache_used": False,
                },
            },
        },
    )
    repository.prune_runs_by_role(
        role="portfolio_market_analysis",
        keep_latest=retention_count,
        max_age_days=retention_days,
    )


def _provider_deployment(provider: ModelProvider) -> str:
    deployment = getattr(provider, "deployment", "cloud")
    return str(getattr(deployment, "value", deployment))


def _safe_source_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def _market_analysis_response(
    analysis: MarketAnalysis,
    *,
    run_id: int,
    style_pack,
    method_documents=(),
    profile=None,
) -> MarketAnalysisResponse:
    dca_allocations = _sector_dca_allocations(analysis, profile=profile)
    return MarketAnalysisResponse(
        run_id=run_id,
        provider=analysis.provider,
        model=analysis.model,
        generated_at=analysis.generated_at,
        content=analysis.content,
        sources=[
            MarketSourceResponse(
                citation_id=source.citation_id,
                title=source.title,
                url=source.url,
                retrieved_at=source.retrieved_at,
            )
            for source in analysis.sources
        ],
        prompt_tokens=analysis.prompt_tokens,
        completion_tokens=analysis.completion_tokens,
        estimated_cost_usd=analysis.estimated_cost_usd,
        source_method=analysis.source_method,
        search_provider=analysis.search_provider,
        search_calls=analysis.search_calls,
        search_estimated_cost_usd=analysis.search_estimated_cost_usd,
        answer_model_estimated_cost_usd=analysis.answer_model_estimated_cost_usd,
        answer_model_calls=getattr(analysis, "answer_model_calls", 1),
        style_pack_id=style_pack.id,
        style_pack_name=style_pack.name,
        method_document_id=(method_documents[0].id if method_documents else None),
        method_document_name=(method_documents[0].name if method_documents else None),
        method_document_ids=[document.id for document in method_documents],
        method_document_names=[document.name for document in method_documents],
        source_count=getattr(analysis, "source_count", len(analysis.sources)),
        domain_count=getattr(analysis, "domain_count", len(analysis.sources)),
        limitations=list(getattr(analysis, "limitations", ())),
        retrieved_result_count=getattr(analysis, "retrieved_result_count", 0),
        retrieved_domain_count=getattr(analysis, "retrieved_domain_count", 0),
        gate_rejected_result_count=getattr(analysis, "gate_rejected_result_count", 0),
        watchlist=[
            MarketWatchlistCandidateResponse(
                symbol=item.symbol,
                name=item.name,
                category=item.category,
                rationale=item.rationale,
                counter_evidence=item.counter_evidence,
                invalidation_signal=item.invalidation_signal,
                overlap_risk=item.overlap_risk,
                dca_guidance=item.dca_guidance,
                dca_suitable=item.dca_suitable,
                dca_monthly_amount=dca_allocations.get(item.symbol, 0.0),
                citation_ids=list(item.citation_ids),
                recommendation_mode=item.recommendation_mode,
            )
            for item in getattr(analysis, "watchlist", ())
        ],
        evidence_snapshot_id=getattr(analysis, "evidence_snapshot_id", ""),
        candidate_parse_status=getattr(
            analysis,
            "candidate_parse_status",
            "not_available",
        ),
        raw_candidate_count=getattr(analysis, "raw_candidate_count", 0),
        candidate_audit=[
            MarketCandidateAuditResponse(
                index=item.index,
                symbol=item.symbol,
                requested_mode=item.requested_mode,
                expected_mode=item.expected_mode,
                supplied_citation_ids=list(item.supplied_citation_ids),
                accepted_citation_ids=list(item.accepted_citation_ids),
                present_fields=list(item.present_fields),
                accepted=item.accepted,
                validation_codes=list(item.validation_codes),
                selection_source=getattr(item, "selection_source", "model"),
                eligible=getattr(item, "eligible", None),
                rank=getattr(item, "rank", None),
                total_score=getattr(item, "total_score", None),
                score_components=dict(getattr(item, "score_components", ())),
                penalties=dict(getattr(item, "penalties", ())),
                market_signal_as_of=getattr(item, "market_signal_as_of", None),
            )
            for item in getattr(analysis, "candidate_audit", ())
        ],
        selection_engine=getattr(analysis, "selection_engine", "model"),
        selection_version=getattr(
            analysis, "selection_version", "selected-model-watchlist-v1"
        ),
        auditor_version=getattr(
            analysis, "auditor_version", "model-output-validator-v1"
        ),
        audit_status=getattr(analysis, "audit_status", "passed"),
        audit_codes=list(getattr(analysis, "audit_codes", ())),
    )


def _sector_dca_allocations(analysis: MarketAnalysis, *, profile) -> dict[str, float]:
    total_budget = float(
        getattr(profile, "monthly_sector_satellite_budget", None) or 0.0
    )
    monthly_contribution = float(getattr(profile, "monthly_contribution", None) or 0.0)
    budget = int(round(max(0.0, min(total_budget, monthly_contribution))))
    eligible = [
        item for item in getattr(analysis, "watchlist", ()) if item.dca_suitable
    ]
    if budget <= 0 or not eligible:
        return {}
    base, remainder = divmod(budget, len(eligible))
    return {
        item.symbol: float(base + (1 if index < remainder else 0))
        for index, item in enumerate(eligible)
    }


def _recommendation_context_response(
    context: RecommendationContext,
) -> RecommendationContextResponse:
    return RecommendationContextResponse(
        status=context.status,
        portfolio_as_of_date=context.portfolio_as_of_date,
        price_source=context.price_source,
        generated_at=context.generated_at,
        live_market_data=context.live_market_data,
        analysis_method=context.analysis_method,
        analysis_method_description=context.analysis_method_description,
        policy=context.policy,
        disclaimer=context.disclaimer,
    )
