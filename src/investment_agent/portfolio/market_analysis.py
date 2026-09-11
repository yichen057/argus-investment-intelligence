from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import uuid4

from investment_agent.harness.types import ToolResult
from investment_agent.portfolio.etf_selection import (
    DETERMINISTIC_AUDITOR_VERSION,
    DETERMINISTIC_SELECTION_VERSION,
    SELECTION_ENGINE_DETERMINISTIC,
    SELECTION_ENGINE_MODEL,
    SUPPORTED_SELECTION_ENGINES,
    EtfSelectionDecision,
    EtfSelectionResult,
    audit_etf_selection,
    select_etf_candidates,
)
from investment_agent.providers.types import ModelProvider, ModelRequest
from investment_agent.search import (
    WebEvidence,
    WebSearchError,
    WebSearchProvider,
    WebSearchResponse,
)

if TYPE_CHECKING:
    from investment_agent.retrieval.vector import RetrievalResult


_PORTFOLIO_MARKET_EVIDENCE_CUES = (
    "federal reserve",
    "interest rates",
    "rate cuts",
    "monetary policy",
    "inflation expectations",
    "inflation outlook",
    "economic growth",
    "earnings growth",
    "earnings outlook",
    "earnings revisions",
    "profit margins",
    "revenue growth",
    "valuation levels",
    "valuation risk",
    "market breadth",
    "credit conditions",
    "fiscal policy",
    "trade policy",
    "regulatory risk",
    "geopolitical risk",
    "central bank",
    "currency moves",
    "gold demand",
    "oil prices",
    "commodity demand",
    "consumer demand",
    "capital spending",
    "supply growth",
)

_SECTOR_MARKET_EVIDENCE_CUES = (
    "sector leadership",
    "sector outlook",
    "industry outlook",
    "industry demand",
    "earnings revisions",
    "earnings growth",
    "profit margins",
    "revenue growth",
    "valuation levels",
    "valuation risk",
    "market breadth",
    "capital spending",
    "semiconductor demand",
    "health care",
    "financial sector",
    "energy sector",
    "technology sector",
    "consumer spending",
)


class MarketAnalysisError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.estimated_cost_usd = estimated_cost_usd


@dataclass(frozen=True)
class MarketSource:
    title: str
    url: str
    retrieved_at: datetime
    citation_id: str


@dataclass(frozen=True)
class MarketWatchlistCandidate:
    symbol: str
    name: str
    category: str
    rationale: str
    counter_evidence: str
    invalidation_signal: str
    overlap_risk: str
    dca_guidance: str
    dca_suitable: bool
    citation_ids: tuple[str, ...]
    recommendation_mode: str = "new_exposure"


@dataclass(frozen=True)
class MarketCandidateAudit:
    index: int
    symbol: str | None
    requested_mode: str | None
    expected_mode: str | None
    supplied_citation_ids: tuple[str, ...]
    accepted_citation_ids: tuple[str, ...]
    present_fields: tuple[str, ...]
    accepted: bool
    validation_codes: tuple[str, ...]
    selection_source: str = SELECTION_ENGINE_MODEL
    eligible: bool | None = None
    rank: int | None = None
    total_score: float | None = None
    score_components: tuple[tuple[str, float], ...] = ()
    penalties: tuple[tuple[str, float], ...] = ()
    market_signal_as_of: str | None = None


@dataclass(frozen=True)
class MarketAnalysis:
    provider: str
    model: str
    generated_at: datetime
    content: str
    sources: tuple[MarketSource, ...]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    source_method: str
    search_provider: str
    search_calls: int
    search_estimated_cost_usd: float
    answer_model_estimated_cost_usd: float
    answer_model_calls: int
    source_count: int
    domain_count: int
    limitations: tuple[str, ...]
    retrieved_result_count: int = 0
    retrieved_domain_count: int = 0
    gate_rejected_result_count: int = 0
    watchlist: tuple[MarketWatchlistCandidate, ...] = ()
    evidence_snapshot_id: str = ""
    candidate_parse_status: str = "not_attempted"
    raw_candidate_count: int = 0
    candidate_audit: tuple[MarketCandidateAudit, ...] = ()
    selection_engine: str = SELECTION_ENGINE_DETERMINISTIC
    selection_version: str = DETERMINISTIC_SELECTION_VERSION
    auditor_version: str = DETERMINISTIC_AUDITOR_VERSION
    audit_status: str = "passed"
    audit_codes: tuple[str, ...] = ()


class IndependentSearchMarketAnalysisService:
    """Retrieve with Exa, gate evidence, then call exactly one selected model."""

    def __init__(
        self,
        *,
        search_provider: WebSearchProvider,
        answer_provider: ModelProvider,
        max_search_calls: int = 2,
        research_candidates: tuple[Any, ...] | list[Any] = (),
        positions: tuple[Any, ...] | list[Any] = (),
        profile: Any | None = None,
        selection_engine: str = SELECTION_ENGINE_DETERMINISTIC,
    ) -> None:
        if max_search_calls not in {1, 2}:
            raise ValueError("Market analysis allows one or two search calls.")
        self._search_provider = search_provider
        self._answer_provider = answer_provider
        self._max_search_calls = max_search_calls
        self._research_candidates = tuple(research_candidates)
        self._positions = tuple(positions)
        self._profile = profile
        normalized_engine = selection_engine.strip().lower()
        if normalized_engine not in SUPPORTED_SELECTION_ENGINES:
            raise ValueError(
                "ETF selection engine must be 'deterministic' or 'model'."
            )
        self._selection_engine = normalized_engine

    def analyze(
        self,
        prompt: str,
        *,
        search_query: str,
        evidence_gate_query: str | None = None,
    ) -> MarketAnalysis:
        from investment_agent.retrieval.evidence_gate import (
            EvidenceDecision,
            evidence_gate_metadata,
        )

        generated_at = datetime.now(timezone.utc)
        candidates: list[RetrievalResult] = []
        evidence_by_chunk: dict[int, WebEvidence] = {}
        search_cost = 0.0
        search_calls = 0
        retrieved_evidence: list[WebEvidence] = []
        gate_query = evidence_gate_query or search_query

        response = self._search(search_query, prior_cost=search_cost)
        search_calls += 1
        search_cost = round(search_cost + response.estimated_cost_usd, 10)
        retrieved_evidence.extend(response.results)
        first_search_domains = _evidence_domains(response.results)
        _append_search_candidates(
            response.results,
            candidates=candidates,
            evidence_by_chunk=evidence_by_chunk,
        )
        gate = _evaluate_market_evidence(
            candidates,
            final_attempt=self._max_search_calls == 1,
            facet="portfolio_drivers",
            fallback_query=gate_query,
        )
        sector_gate = None

        if self._max_search_calls > 1:
            peer_symbols = _candidate_peer_comparison_symbols(
                self._positions,
                self._research_candidates,
            )
            peer_scope = " ".join(peer_symbols)
            follow_up_query = (
                "current sector leadership earnings revisions valuation breadth "
                "counter evidence ETF peer comparison same-window total return "
                f"expense ratio assets liquidity {peer_scope} {search_query}"
                if gate.decision is EvidenceDecision.SUPPORTED
                else f"{gate.follow_up_query or gate_query} {search_query}"
            )
            response = self._search(
                follow_up_query,
                prior_cost=search_cost,
                exclude_domains=tuple(sorted(first_search_domains)),
            )
            search_calls += 1
            search_cost = round(search_cost + response.estimated_cost_usd, 10)
            retrieved_evidence.extend(response.results)
            second_facet_start = len(candidates)
            _append_search_candidates(
                response.results,
                candidates=candidates,
                evidence_by_chunk=evidence_by_chunk,
            )
            second_facet_candidates = candidates[second_facet_start:]
            sector_gate = _evaluate_market_evidence(
                second_facet_candidates,
                final_attempt=True,
                facet="sector_outlook",
                fallback_query="sector outlook",
            )
            gate = _evaluate_market_evidence(
                candidates,
                final_attempt=True,
                facet="portfolio_drivers",
                fallback_query=gate_query,
            )

        if gate.decision is not EvidenceDecision.SUPPORTED:
            raise MarketAnalysisError(
                "insufficient_market_evidence",
                "Exa returned results, but the Evidence Gate found no complete "
                "passage that directly supported the requested market context. The "
                "selected answer model was not called.",
                estimated_cost_usd=search_cost,
            )

        accepted_items = list(gate.accepted)
        if (
            sector_gate is not None
            and sector_gate.decision is EvidenceDecision.SUPPORTED
        ):
            seen_chunk_ids = {item.result.chunk_id for item in accepted_items}
            accepted_items.extend(
                item
                for item in sector_gate.accepted
                if item.result.chunk_id not in seen_chunk_ids
            )
        accepted_items = _select_domain_diverse_evidence(accepted_items, limit=8)

        rows: list[dict[str, object]] = []
        sources: list[MarketSource] = []
        for accepted in accepted_items:
            evidence = evidence_by_chunk.get(accepted.result.chunk_id)
            if evidence is None:
                continue
            citation_id = f"W{len(rows) + 1}"
            rows.append(
                {
                    "citation_id": citation_id,
                    "evidence_item_id": None,
                    "supported_passage": accepted.supported_passage,
                    "text": accepted.supported_passage,
                    "source_uri": evidence.url,
                    "source_type": "web",
                    "title": evidence.title,
                    "publication_date": (
                        evidence.published_at.date().isoformat()
                        if evidence.published_at is not None
                        else None
                    ),
                    "retrieved_at": evidence.retrieved_at.isoformat(),
                }
            )
            sources.append(
                MarketSource(
                    citation_id=citation_id,
                    title=evidence.title,
                    url=evidence.url,
                    retrieved_at=evidence.retrieved_at,
                )
            )

        domains = {
            _source_domain(source.url)
            for source in sources
            if _source_domain(source.url)
        }

        if not rows:
            raise MarketAnalysisError(
                "insufficient_market_evidence",
                "No accepted direct-URL evidence remained after validation. The "
                "selected answer model was not called.",
                estimated_cost_usd=search_cost,
            )
        limitations: list[str] = []
        if len(domains) < 2:
            limitations.append(
                "Only one independent source domain passed the Evidence Gate. Treat "
                "the synthesis as a limited-source view and verify it against another "
                "current primary source before acting."
            )
        retrieved_keys = {item.evidence_key for item in retrieved_evidence}
        retrieved_domains = _evidence_domains(tuple(retrieved_evidence))

        fixed_selection = None
        independent_audit = None
        if self._selection_engine == SELECTION_ENGINE_DETERMINISTIC:
            fixed_selection = select_etf_candidates(
                candidates=self._research_candidates,
                positions=self._positions,
                profile=self._profile,
                evidence_rows=rows,
                generated_at=generated_at,
            )
            independent_audit = audit_etf_selection(
                fixed_selection,
                candidates=self._research_candidates,
                positions=self._positions,
                allowed_citation_ids={str(row["citation_id"]) for row in rows},
            )
            if independent_audit.status != "passed":
                raise MarketAnalysisError(
                    "etf_selection_audit_failed",
                    "The independent deterministic ETF auditor rejected the fixed "
                    "ranking before the answer model was called.",
                    estimated_cost_usd=search_cost,
                )

        tool_result = ToolResult(
            call_id=f"portfolio-market-{uuid4().hex[:12]}",
            status="ok",
            output={
                "search": {
                    "provider": self._search_provider.provider_name,
                    "search_calls": search_calls,
                    "search_estimated_cost_usd": search_cost,
                    "evidence_gate": evidence_gate_metadata(gate),
                    "facet_gates": {
                        "portfolio_drivers": evidence_gate_metadata(gate),
                        "sector_outlook": (
                            evidence_gate_metadata(sector_gate)
                            if sector_gate is not None
                            else None
                        ),
                    },
                    "source_diversity": {
                        "accepted_domains": sorted(domains),
                        "minimum_preferred": 2,
                        "status": "preferred" if len(domains) >= 2 else "limited",
                    },
                },
                "results": rows,
            },
        )
        synthesis_prompt = prompt
        if fixed_selection is not None:
            synthesis_prompt += _fixed_selection_prompt(fixed_selection.decisions)
        if limitations:
            synthesis_prompt += (
                "\nEvidence diversity limitation: "
                + " ".join(limitations)
                + " State this limitation prominently and do not call the analysis comprehensive."
            )
        model_responses = [
            self._answer_provider.generate(
                ModelRequest(
                    objective=synthesis_prompt,
                    role="portfolio_market_analysis",
                    sensitivity="public",
                    as_of_date=generated_at.date(),
                    tool_results=(tool_result,),
                    iteration=search_calls,
                )
            )
        ]
        model_response = model_responses[-1]
        model_cost = model_response.estimated_cost_usd
        total_cost = round(search_cost + model_cost, 10)
        if not model_response.success or model_response.tool_call is not None:
            code = model_response.error_code or "answer_model_provider_error"
            raise MarketAnalysisError(
                code,
                "The selected answer model failed after Exa returned accepted "
                "evidence. Argus did not switch models.",
                prompt_tokens=model_response.prompt_tokens,
                completion_tokens=model_response.completion_tokens,
                estimated_cost_usd=total_cost,
            )

        allowed_citation_ids = {source.citation_id for source in sources}
        content = _normalize_known_citations(
            model_response.content,
            allowed_citation_ids=allowed_citation_ids,
        )
        content = _attach_verifiable_market_citations(content, evidence_rows=rows)
        if (
            _citation_status(
                content,
                allowed_citation_ids=allowed_citation_ids,
            )
            != "validated"
        ):
            repair_prompt = (
                synthesis_prompt
                + "\nCitation repair requirement: Return a complete replacement answer, "
                "not a critique of the previous draft. Every factual statement based on "
                "the supplied evidence must use exact citation tokens from this allowlist: "
                + ", ".join(
                    f"[source:{citation_id}]"
                    for citation_id in sorted(allowed_citation_ids)
                )
                + ". Put each ID in its own bracket; never combine IDs inside one bracket. "
                "Omit any claim or watchlist candidate that cannot be directly cited."
            )
            repaired_response = self._answer_provider.generate(
                ModelRequest(
                    objective=repair_prompt,
                    role="portfolio_market_analysis_citation_repair",
                    sensitivity="public",
                    as_of_date=generated_at.date(),
                    tool_results=(tool_result,),
                    iteration=search_calls + 1,
                )
            )
            model_responses.append(repaired_response)
            model_response = repaired_response
            model_cost = sum(
                response.estimated_cost_usd for response in model_responses
            )
            total_cost = round(search_cost + model_cost, 10)
            if not model_response.success or model_response.tool_call is not None:
                code = model_response.error_code or "answer_model_provider_error"
                raise MarketAnalysisError(
                    code,
                    "The selected answer model failed during the one bounded citation "
                    "repair call. Argus did not switch models.",
                    prompt_tokens=sum(
                        response.prompt_tokens for response in model_responses
                    ),
                    completion_tokens=sum(
                        response.completion_tokens for response in model_responses
                    ),
                    estimated_cost_usd=total_cost,
                )
            content = _normalize_known_citations(
                model_response.content,
                allowed_citation_ids=allowed_citation_ids,
            )
            content = _attach_verifiable_market_citations(content, evidence_rows=rows)

        if (
            _citation_status(
                content,
                allowed_citation_ids=allowed_citation_ids,
            )
            != "validated"
        ):
            raise MarketAnalysisError(
                "invalid_market_analysis_citations",
                "The selected answer model still did not cite supplied Exa evidence "
                "with valid source IDs after one bounded same-model repair, so Argus "
                "rejected the analysis.",
                prompt_tokens=sum(
                    response.prompt_tokens for response in model_responses
                ),
                completion_tokens=sum(
                    response.completion_tokens for response in model_responses
                ),
                estimated_cost_usd=total_cost,
            )

        (
            clean_content,
            model_watchlist,
            model_candidate_parse_status,
            raw_candidate_count,
            model_candidate_audit,
        ) = _extract_watchlist(
            content,
            research_candidates=self._research_candidates,
            allowed_citation_ids=allowed_citation_ids,
            held_symbols={
                str(position.symbol).strip().upper() for position in self._positions
            },
        )
        if fixed_selection is not None:
            watchlist = _fixed_watchlist(
                fixed_selection.decisions,
                model_watchlist=model_watchlist,
            )
            candidate_parse_status = (
                "deterministic_fixed_model_explanations_valid"
                if _model_explanations_match_fixed_selection(
                    fixed_selection.decisions,
                    model_watchlist,
                )
                else "deterministic_fixed_model_explanations_fallback"
            )
            candidate_audit = _fixed_candidate_audit(fixed_selection)
        else:
            watchlist = model_watchlist
            candidate_parse_status = model_candidate_parse_status
            candidate_audit = model_candidate_audit
        return MarketAnalysis(
            provider=model_response.provider,
            model=model_response.model,
            generated_at=generated_at,
            content=clean_content,
            sources=tuple(sources),
            prompt_tokens=sum(response.prompt_tokens for response in model_responses),
            completion_tokens=sum(
                response.completion_tokens for response in model_responses
            ),
            estimated_cost_usd=total_cost,
            source_method=(
                f"{self._search_provider.provider_name.title()} Search + Argus "
                "Evidence Gate + "
                + (
                    "Deterministic ETF Rank + "
                    if fixed_selection is not None
                    else "Legacy Model ETF Selection + "
                )
                + f"{model_response.model} synthesis"
            ),
            search_provider=self._search_provider.provider_name,
            search_calls=search_calls,
            search_estimated_cost_usd=search_cost,
            answer_model_estimated_cost_usd=model_cost,
            answer_model_calls=len(model_responses),
            source_count=len(sources),
            domain_count=len(domains),
            limitations=tuple(limitations),
            retrieved_result_count=len(retrieved_keys),
            retrieved_domain_count=len(retrieved_domains),
            gate_rejected_result_count=max(0, len(retrieved_keys) - len(sources)),
            watchlist=watchlist,
            evidence_snapshot_id=_evidence_snapshot_id(rows),
            candidate_parse_status=candidate_parse_status,
            raw_candidate_count=raw_candidate_count,
            candidate_audit=candidate_audit,
            selection_engine=self._selection_engine,
            selection_version=(
                DETERMINISTIC_SELECTION_VERSION
                if fixed_selection is not None
                else "selected-model-watchlist-v1"
            ),
            auditor_version=(
                DETERMINISTIC_AUDITOR_VERSION
                if independent_audit is not None
                else "model-output-validator-v1"
            ),
            audit_status=(
                independent_audit.status if independent_audit is not None else "passed"
            ),
            audit_codes=(
                independent_audit.codes if independent_audit is not None else ()
            ),
        )

    def _search(
        self,
        query: str,
        *,
        prior_cost: float,
        exclude_domains: tuple[str, ...] = (),
    ) -> WebSearchResponse:
        try:
            return self._search_provider.search(
                query,
                exclude_domains=exclude_domains,
            )
        except WebSearchError as exc:
            raise MarketAnalysisError(
                exc.code,
                str(exc),
                estimated_cost_usd=prior_cost + exc.estimated_cost_usd,
            ) from exc


def market_prompt(
    positions: list[Any],
    *,
    portfolio_as_of: str,
    policy_actions: list[Any] | tuple[Any, ...] = (),
    research_candidates: list[Any] | tuple[Any, ...] = (),
    style_context: str | None = None,
    profile: Any | None = None,
    selection_engine: str = SELECTION_ENGINE_DETERMINISTIC,
) -> str:
    total_value = sum(max(0.0, float(position.market_value)) for position in positions)
    holdings = [
        {
            "symbol": str(position.symbol),
            "asset_class": str(position.asset_class),
            "portfolio_weight": (
                round(max(0.0, float(position.market_value)) / total_value, 4)
                if total_value > 0
                else 0.0
            ),
        }
        for position in sorted(
            positions,
            key=lambda item: float(item.market_value),
            reverse=True,
        )[:12]
    ]
    actions = [
        {
            "action": str(action.action),
            "symbol": str(action.symbol or ""),
            "asset_class": str(action.asset_class),
            "current_weight": round(float(action.current_weight), 4),
            "policy_reference_weight": round(float(action.target_weight), 4),
        }
        for action in policy_actions
    ]
    exact_held_symbols = {
        str(position.symbol).strip().upper() for position in positions
    }
    candidates = [
        {
            "symbol": str(candidate.symbol),
            "name": str(candidate.name),
            "issuer": str(getattr(candidate, "issuer", "") or ""),
            "exposure_key": str(getattr(candidate, "exposure_key", "") or ""),
            "portfolio_role": str(candidate.portfolio_role),
            "related_direct_stock_holdings": list(
                getattr(candidate, "related_holdings", ()) or ()
            ),
            "exact_etf_held": str(candidate.symbol).strip().upper()
            in exact_held_symbols,
        }
        for candidate in research_candidates
    ]
    profile_context = {
        "risk_tolerance": getattr(profile, "risk_tolerance", None),
        "investment_horizon": getattr(profile, "investment_horizon", None),
        "investing_experience": getattr(profile, "investing_experience", None),
        "liquidity_needs": getattr(profile, "liquidity_needs", None),
        "preferred_style": getattr(profile, "preferred_style", None),
        "rebalance_preference": getattr(profile, "rebalance_preference", None),
    }
    candidate_instruction = (
        "The structured sector watchlist must rank one to three candidates "
        "from the supplied controlled universe whenever accepted evidence can support at "
        "least one defensible candidate. Candidate selection is independent of whether the "
        "user has entered a dollar budget. "
        if selection_engine == SELECTION_ENGINE_MODEL
        else "Argus will append a fixed-ranked candidate list after evidence scoring. "
        "The structured sector watchlist must explain exactly that list; the model must "
        "not choose, add, remove, replace, or reorder ETF symbols. "
    )
    return (
        "Prepare a concise current market background for this portfolio. Cover the "
        "main macro drivers, asset-specific factors, counter-evidence, and what the "
        "investor should verify next. For each supplied policy action, explain current "
        "market evidence that supports caution and evidence that argues against acting "
        "now; the saved allocation policy remains the reason for the trade. Use only "
        "the supplied Exa evidence, state the date of every time-sensitive fact when "
        "available, and cite claims with the supplied [source:ID]. Prefer central "
        "banks, regulators, government data, index providers, and fund issuers over "
        "promotional or affiliate commentary. Before the readable analysis, output exactly "
        "one fenced ```argus-sector-watchlist JSON block with a JSON array. Producing this "
        "block first is mandatory so it cannot be lost when the provider reaches its output "
        "limit. After that block, use short Markdown sections and bullets, not one long "
        "paragraph. Stay under 650 words, do not repeat the full watchlist fields in prose, "
        "and finish every section rather than ending mid-sentence. Do not change any "
        "portfolio weight or calculate trades.\n"
        + candidate_instruction
        + "Treat existing exposure as a portfolio-fit gate, "
        "not merely a disclosure. Use recommendation_mode='new_exposure' only when neither "
        "the exact ETF nor mapped related stocks are held. If related direct stocks are held, "
        "the ETF may appear only as recommendation_mode='diversifying_replacement': explain "
        "that it would replace or reduce those stocks rather than be added on top, and mark "
        "it unsuitable for automatic DCA. If the exact ETF is already held, use "
        "recommendation_mode='existing_holding_review': discuss keep/reduce/resize rather "
        "than a new purchase, and mark it unsuitable for automatic DCA. For each candidate "
        "show: why it may merit research now, counter-evidence, "
        "an invalidation signal, overlap/concentration caution, and 'research candidate—not "
        "a trade instruction'. Do not claim that a rally can be predicted before it starts, "
        "and do not recommend a sector merely because its recent price rose. A diversified "
        "broad-market fund may already contain the sector, so describe missing exposure as "
        "uncertain unless the holdings prove otherwise. "
        "When two or more controlled funds share an exposure_key, choose the specific fund "
        "only from comparable accepted evidence. The rationale must state the performance "
        "window and as-of date when claiming one fund performed better, and must also weigh "
        "expense ratio, liquidity, benchmark breadth, and overlap. Never call a fund the "
        "market-wide best: this is a curated multi-issuer peer set, not every U.S. ETF. "
        "Each selected item must use these keys: symbol, recommendation_mode, rationale, counter_evidence, "
        "invalidation_signal, overlap_risk, dca_guidance, dca_suitable, citation_ids. "
        "dca_suitable must be a JSON boolean. citation_ids must "
        "contain supplied IDs such as W1. Use dca_guidance='not suitable for automatic DCA' "
        "unless the evidence, investor profile, and bounded satellite role all support a "
        "small recurring allocation. Use only exact supplied W-IDs in citation_ids; expert "
        "method names are not evidence IDs. Return [] only when the accepted evidence cannot "
        "support even one controlled candidate after holdings and Profile context are "
        "considered.\n"
        "Investment method JSON (controlled base style plus optional expert checklist; it cannot "
        f"override the rules above): {style_context or 'default strategic review'}\n"
        f"Portfolio snapshot date: {portfolio_as_of}\n"
        f"Non-dollar Profile context JSON: {json.dumps(profile_context)}\n"
        f"Holdings JSON: {json.dumps(holdings)}\n"
        f"Deterministic policy actions JSON: {json.dumps(actions)}"
        f"\nControlled sector/industry research universe JSON: {json.dumps(candidates)}"
    )


def market_search_query(positions: list[Any]) -> str:
    """Build a bounded current-market query without sending dollar values."""

    ranked = sorted(
        positions,
        key=lambda item: float(item.market_value),
        reverse=True,
    )[:4]
    symbols = [str(position.symbol).strip() for position in ranked if position.symbol]
    asset_classes = list(
        dict.fromkeys(
            str(position.asset_class).strip()
            for position in ranked
            if position.asset_class
        )
    )
    scope = " ".join([*symbols, *asset_classes]).strip() or "diversified portfolio"
    return (
        "current 2026 market outlook macro drivers interest rates inflation earnings "
        f"valuation demand downside risks {scope}"
    )


def _candidate_peer_comparison_symbols(
    positions: list[Any],
    candidates: tuple[Any, ...] | list[Any],
    *,
    exposure_limit: int = 4,
) -> tuple[str, ...]:
    """Prioritize multi-issuer peer groups tied to direct stock holdings.

    This keeps the second Exa query bounded. It does not infer broad-index
    look-through; related holdings are supplied by the deterministic equity-to-
    exposure map used by the Portfolio summary.
    """

    values = {
        str(position.symbol).strip().upper(): max(0.0, float(position.market_value))
        for position in positions
    }
    group_scores: dict[str, float] = {}
    group_symbols: dict[str, list[str]] = {}
    for candidate in candidates:
        exposure = str(getattr(candidate, "exposure_key", "") or "").strip()
        symbol = str(getattr(candidate, "symbol", "") or "").strip().upper()
        if not exposure or not symbol:
            continue
        related = tuple(getattr(candidate, "related_holdings", ()) or ())
        if not related:
            continue
        group_scores[exposure] = max(
            group_scores.get(exposure, 0.0),
            sum(values.get(str(item).upper(), 0.0) for item in related),
        )
        group_symbols.setdefault(exposure, []).append(symbol)

    selected: list[str] = []
    for exposure, _ in sorted(
        group_scores.items(),
        key=lambda item: (-item[1], item[0]),
    )[:exposure_limit]:
        selected.extend(sorted(dict.fromkeys(group_symbols[exposure])))
    return tuple(dict.fromkeys(selected))


def market_evidence_gate_query() -> str:
    """Check for a complete risk/driver statement, not all tickers in one passage."""

    return "market risk drivers"


def _evaluate_market_evidence(
    results: list[RetrievalResult],
    *,
    final_attempt: bool,
    facet: str,
    fallback_query: str,
):
    """Apply the shared passage checks through market-specific evidence slots.

    A portfolio market analysis is intentionally multi-topic. Requiring every useful
    passage to repeat the literal words "market risk drivers" produced false negatives,
    even when Exa returned a complete statement about rates, earnings, valuation, or
    sector demand. Each cue below remains deterministic and still uses EvidenceGate's
    sentence-completeness, year, and direct-overlap checks.
    """

    from investment_agent.retrieval.evidence_gate import (
        AcceptedEvidence,
        EvidenceDecision,
        EvidenceGate,
        EvidenceGateResult,
    )

    cues = (
        _SECTOR_MARKET_EVIDENCE_CUES
        if facet == "sector_outlook"
        else _PORTFOLIO_MARKET_EVIDENCE_CUES + _SECTOR_MARKET_EVIDENCE_CUES
    )
    accepted: list[AcceptedEvidence] = []
    seen_chunk_ids: set[int] = set()
    matched_cues: list[str] = []
    for cue in cues:
        cue_result = EvidenceGate().evaluate(cue, results, final_attempt=True)
        cue_added = False
        for item in cue_result.accepted:
            chunk_id = int(item.result.chunk_id)
            if chunk_id in seen_chunk_ids:
                continue
            accepted.append(item)
            seen_chunk_ids.add(chunk_id)
            cue_added = True
        if cue_added:
            matched_cues.append(cue)

    if accepted:
        combined_word_count = len(
            re.findall(
                r"\b[\w'-]+\b",
                " ".join(item.supported_passage for item in accepted),
            )
        )
        return EvidenceGateResult(
            decision=EvidenceDecision.SUPPORTED,
            accepted=tuple(accepted),
            gap_id=None,
            material_gaps=(),
            follow_up_query=None,
            report_eligible=combined_word_count >= 18 or len(accepted) >= 2,
            reasons=(
                "Complete passages directly matched deterministic market evidence slots: "
                + ", ".join(matched_cues[:6])
                + ".",
            ),
            evaluated_candidate_count=len(results),
        )

    return EvidenceGate().evaluate(
        fallback_query,
        results,
        final_attempt=final_attempt,
    )


def _append_search_candidates(
    evidence_items: tuple[WebEvidence, ...],
    *,
    candidates: list[RetrievalResult],
    evidence_by_chunk: dict[int, WebEvidence],
) -> None:
    from investment_agent.retrieval.vector import RetrievalResult

    seen_keys = {item.evidence_key for item in evidence_by_chunk.values()}
    for evidence in evidence_items:
        if evidence.evidence_key in seen_keys:
            continue
        chunk_id = -(len(evidence_by_chunk) + 1)
        score = max(evidence.highlight_scores, default=0.5)
        evidence_by_chunk[chunk_id] = evidence
        candidates.append(
            RetrievalResult(
                chunk_id=chunk_id,
                document_id=-1,
                evidence_item_id=None,
                score=score,
                text=evidence.passage,
                source_uri=evidence.url,
                source_type="web",
                title=evidence.title,
                page_or_section=None,
                evidence_grade="public_web_extract",
                excerpt=evidence.passage,
                publication_date=(
                    evidence.published_at.date()
                    if evidence.published_at is not None
                    else None
                ),
                fused_score=score,
                match_signals=("exa", "extractive_highlight"),
                context_text=evidence.text or evidence.passage,
            )
        )
        seen_keys.add(evidence.evidence_key)


def _citation_status(content: str, *, allowed_citation_ids: set[str]) -> str:
    citations = set(re.findall(r"\[source:([A-Za-z0-9_-]+)\]", content))
    if not citations:
        return "missing"
    if not citations <= allowed_citation_ids:
        return "invalid"
    return "validated"


def _normalize_known_citations(
    content: str,
    *,
    allowed_citation_ids: set[str],
) -> str:
    def replacement(match: re.Match[str]) -> str:
        citation_ids = [
            value.upper()
            for value in re.findall(
                r"[A-Za-z][A-Za-z0-9_-]*",
                match.group("ids"),
            )
        ]
        if not citation_ids or not set(citation_ids) <= allowed_citation_ids:
            return match.group(0)
        return " ".join(f"[source:{citation_id}]" for citation_id in citation_ids)

    citation_list = (
        r"(?P<ids>[A-Za-z][A-Za-z0-9_-]*"
        r"(?:\s*(?:[/,;，、&]|\band\b)\s*[A-Za-z][A-Za-z0-9_-]*)*)"
    )
    normalized = re.sub(
        rf"[\[【(（]\s*source\s*[:：]?\s*{citation_list}\s*[\]】)）]",
        replacement,
        content,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"(?<![\[【])\bsource\s*[:：]?\s*{citation_list}",
        replacement,
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"[\[【]\s*{citation_list}\s*[\]】]",
        replacement,
        normalized,
        flags=re.IGNORECASE,
    )

    # DeepSeek and some OpenAI-compatible models often rewrite supplied W1 IDs
    # as numeric Markdown footnotes. The mapping is safe only when the resulting
    # W-number is in the exact allowlist provided to that request.
    def ordinal_replacement(match: re.Match[str]) -> str:
        citation_id = f"W{int(match.group('ordinal'))}"
        return (
            f"[source:{citation_id}]"
            if citation_id in allowed_citation_ids
            else match.group(0)
        )

    return re.sub(
        r"[\[【]\s*\^?(?P<ordinal>\d{1,2})\s*[\]】]",
        ordinal_replacement,
        normalized,
    )


_MARKET_CITATION_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "because",
    "before",
    "but",
    "current",
    "does",
    "from",
    "have",
    "into",
    "market",
    "more",
    "not",
    "only",
    "portfolio",
    "research",
    "that",
    "the",
    "their",
    "this",
    "through",
    "under",
    "with",
}


def _attach_verifiable_market_citations(
    content: str,
    *,
    evidence_rows: list[dict[str, object]],
) -> str:
    """Attach a citation only when a prose line overlaps one accepted passage.

    This is a deterministic format repair, not an evidence inference. It handles
    models that paraphrase accepted evidence but omit Argus's bracket syntax. A line
    without at least three meaningful shared terms is left untouched and can still
    cause the response to fail closed.
    """

    if _WATCHLIST_BLOCK.search(content):
        prose, watchlist_block = _split_watchlist_block(content)
    else:
        prose, watchlist_block = content, ""

    evidence_terms = [
        (
            str(row.get("citation_id") or ""),
            _market_citation_terms(str(row.get("supported_passage") or "")),
        )
        for row in evidence_rows
    ]
    repaired_lines: list[str] = []
    for line in prose.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or "[source:" in stripped.lower()
            or len(_market_citation_terms(stripped)) < 4
        ):
            repaired_lines.append(line)
            continue
        line_terms = _market_citation_terms(stripped)
        ranked = sorted(
            (
                (len(line_terms & terms), citation_id)
                for citation_id, terms in evidence_terms
                if citation_id
            ),
            reverse=True,
        )
        best_overlap, best_citation_id = ranked[0] if ranked else (0, "")
        if best_overlap >= 3:
            repaired_lines.append(f"{line.rstrip()} [source:{best_citation_id}]")
        else:
            repaired_lines.append(line)
    repaired = "\n".join(repaired_lines).strip()
    return f"{repaired}\n{watchlist_block}".strip() if watchlist_block else repaired


def _market_citation_terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", value.lower())
        if len(term) >= 3 and term not in _MARKET_CITATION_STOPWORDS
    }


def _split_watchlist_block(content: str) -> tuple[str, str]:
    match = _WATCHLIST_BLOCK.search(content)
    if match is None:
        return content, ""
    return (
        (content[: match.start()] + content[match.end() :]).strip(),
        match.group(0),
    )


def _source_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def _evidence_domains(items: tuple[WebEvidence, ...]) -> set[str]:
    return {domain for item in items if (domain := _source_domain(item.url))}


def _select_domain_diverse_evidence(
    items: list[Any],
    *,
    limit: int,
) -> list[Any]:
    """Prefer one accepted passage per domain before adding same-domain extras."""

    selected: list[Any] = []
    deferred: list[Any] = []
    seen_domains: set[str] = set()
    seen_chunk_ids: set[int] = set()

    for item in items:
        chunk_id = int(item.result.chunk_id)
        if chunk_id in seen_chunk_ids:
            continue
        domain = _source_domain(str(item.result.source_uri))
        if domain and domain not in seen_domains:
            selected.append(item)
            seen_domains.add(domain)
            seen_chunk_ids.add(chunk_id)
        else:
            deferred.append(item)
        if len(selected) >= limit:
            return selected

    for item in deferred:
        chunk_id = int(item.result.chunk_id)
        if chunk_id in seen_chunk_ids:
            continue
        selected.append(item)
        seen_chunk_ids.add(chunk_id)
        if len(selected) >= limit:
            break
    return selected


def _evidence_snapshot_id(rows: list[dict[str, object]]) -> str:
    """Return a stable identifier without copying accepted passage text."""

    identity = [
        {
            "citation_id": str(row.get("citation_id") or ""),
            "source_uri": str(row.get("source_uri") or ""),
            "publication_date": str(row.get("publication_date") or ""),
            "retrieved_at": str(row.get("retrieved_at") or ""),
        }
        for row in rows
    ]
    encoded = json.dumps(
        identity,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


_WATCHLIST_BLOCK = re.compile(
    r"```argus-sector-watchlist\s*(?P<payload>\[.*?\])\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)


def _fixed_selection_prompt(
    decisions: tuple[EtfSelectionDecision, ...],
) -> str:
    payload = [
        {
            "rank": item.rank,
            "symbol": item.symbol,
            "recommendation_mode": item.recommendation_mode,
            "citation_ids": list(item.citation_ids),
            "total_score": item.total_score,
            "score_components": dict(item.score_components),
            "penalties": dict(item.penalties),
            "market_signal_as_of": item.market_signal_as_of,
        }
        for item in decisions
    ]
    return (
        "\nETF selection-engine boundary: Argus has already applied hard eligibility, "
        "Profile/holdings fit, timestamped market signals, evidence quality, and "
        "overlap/concentration/expense/liquidity penalties. The following fixed-ranked "
        "JSON is the complete candidate list: "
        f"{json.dumps(payload)}. Do not add, remove, replace, or reorder symbols. "
        "Use the required argus-sector-watchlist block only to explain these exact "
        "decisions with the supplied citation IDs. If the list is empty, return []."
    )


def _model_explanations_match_fixed_selection(
    decisions: tuple[EtfSelectionDecision, ...],
    model_watchlist: tuple[MarketWatchlistCandidate, ...],
) -> bool:
    if [item.symbol for item in model_watchlist] != [
        item.symbol for item in decisions
    ]:
        return False
    return all(
        explanation.recommendation_mode == decision.recommendation_mode
        and explanation.dca_suitable == decision.dca_suitable
        and bool(explanation.citation_ids)
        and set(explanation.citation_ids).issubset(decision.citation_ids)
        for decision, explanation in zip(decisions, model_watchlist, strict=True)
    )


def _fixed_watchlist(
    decisions: tuple[EtfSelectionDecision, ...],
    *,
    model_watchlist: tuple[MarketWatchlistCandidate, ...],
) -> tuple[MarketWatchlistCandidate, ...]:
    use_model_explanations = _model_explanations_match_fixed_selection(
        decisions,
        model_watchlist,
    )
    model_by_symbol = {item.symbol: item for item in model_watchlist}
    result: list[MarketWatchlistCandidate] = []
    for item in decisions:
        explanation = model_by_symbol.get(item.symbol) if use_model_explanations else None
        result.append(
            MarketWatchlistCandidate(
                symbol=item.symbol,
                name=item.name,
                category=item.category,
                rationale=(
                    explanation.rationale if explanation is not None else item.rationale
                ),
                counter_evidence=(
                    explanation.counter_evidence
                    if explanation is not None
                    else item.counter_evidence
                ),
                invalidation_signal=(
                    explanation.invalidation_signal
                    if explanation is not None
                    else item.invalidation_signal
                ),
                overlap_risk=(
                    explanation.overlap_risk
                    if explanation is not None
                    else item.overlap_risk
                ),
                dca_guidance=item.dca_guidance,
                dca_suitable=item.dca_suitable,
                citation_ids=item.citation_ids,
                recommendation_mode=item.recommendation_mode,
            )
        )
    return tuple(result)


def _fixed_candidate_audit(
    selection: EtfSelectionResult,
) -> tuple[MarketCandidateAudit, ...]:
    return tuple(
        MarketCandidateAudit(
            index=item.index,
            symbol=item.symbol,
            requested_mode=None,
            expected_mode=item.expected_mode,
            supplied_citation_ids=item.citation_ids,
            accepted_citation_ids=item.citation_ids,
            present_fields=(
                "hard_eligibility",
                "profile_holdings_fit",
                "timestamped_market_signal",
                "evidence_quality",
                "penalties",
            ),
            accepted=item.selected,
            validation_codes=item.validation_codes,
            selection_source=SELECTION_ENGINE_DETERMINISTIC,
            eligible=item.eligible,
            rank=item.rank,
            total_score=item.total_score,
            score_components=item.score_components,
            penalties=item.penalties,
            market_signal_as_of=item.market_signal_as_of,
        )
        for item in selection.outcomes
    )


def _extract_watchlist(
    content: str,
    *,
    research_candidates: tuple[Any, ...] | list[Any],
    allowed_citation_ids: set[str],
    held_symbols: set[str] | None = None,
) -> tuple[
    str,
    tuple[MarketWatchlistCandidate, ...],
    str,
    int,
    tuple[MarketCandidateAudit, ...],
]:
    match = _WATCHLIST_BLOCK.search(content)
    clean_content = _WATCHLIST_BLOCK.sub("", content).strip()
    if match is None:
        return clean_content, (), "missing_block", 0, ()
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return clean_content, (), "invalid_json", 0, ()
    if not isinstance(payload, list):
        return clean_content, (), "invalid_payload_type", 0, ()
    allowed = {
        str(candidate.symbol).upper(): candidate for candidate in research_candidates
    }
    exact_holdings = {value.upper() for value in (held_symbols or set())}
    accepted: list[MarketWatchlistCandidate] = []
    audit: list[MarketCandidateAudit] = []
    for index, item in enumerate(payload[:10]):
        if not isinstance(item, dict):
            audit.append(
                MarketCandidateAudit(
                    index=index,
                    symbol=None,
                    requested_mode=None,
                    expected_mode=None,
                    supplied_citation_ids=(),
                    accepted_citation_ids=(),
                    present_fields=(),
                    accepted=False,
                    validation_codes=("invalid_candidate_object",),
                )
            )
            continue
        symbol = str(item.get("symbol") or "").upper()
        candidate = allowed.get(symbol)
        supplied_citation_ids = tuple(
            dict.fromkeys(
                str(value).upper() for value in (item.get("citation_ids") or [])
            )
        )
        citation_ids = tuple(
            dict.fromkeys(
                value
                for value in supplied_citation_ids
                if value in allowed_citation_ids
            )
        )
        fields = {
            key: str(item.get(key) or "").strip()
            for key in (
                "rationale",
                "counter_evidence",
                "invalidation_signal",
                "overlap_risk",
                "dca_guidance",
            )
        }
        dca_suitable = item.get("dca_suitable")
        recommendation_mode = str(item.get("recommendation_mode") or "").strip()
        related_holdings = (
            tuple(getattr(candidate, "related_holdings", ()) or ())
            if candidate is not None
            else ()
        )
        expected_mode = (
            (
                "existing_holding_review"
                if symbol in exact_holdings
                else "diversifying_replacement"
                if related_holdings
                else "new_exposure"
            )
            if candidate is not None
            else None
        )
        validation_codes: list[str] = []
        if index >= 3:
            validation_codes.append("candidate_limit_exceeded")
        if not symbol:
            validation_codes.append("missing_symbol")
        elif candidate is None:
            validation_codes.append("not_in_controlled_universe")
        if not supplied_citation_ids:
            validation_codes.append("missing_citation_ids")
        elif not citation_ids:
            validation_codes.append("no_accepted_citation")
        elif len(citation_ids) < len(supplied_citation_ids):
            validation_codes.append("unknown_citation_removed")
        missing_fields = tuple(key for key, value in fields.items() if not value)
        if missing_fields:
            validation_codes.append("missing_required_fields")
        if not isinstance(dca_suitable, bool):
            validation_codes.append("invalid_dca_suitable")
        if expected_mode is not None and recommendation_mode != expected_mode:
            validation_codes.append("recommendation_mode_conflict")
        decision_language = " ".join(fields.values()).lower()
        if expected_mode == "diversifying_replacement" and not any(
            token in decision_language
            for token in (
                "replace",
                "replacement",
                "reduce",
                "trim",
                "substitut",
                "替代",
                "减持",
                "降低",
            )
        ):
            validation_codes.append("missing_replacement_language")
        if expected_mode == "existing_holding_review" and not any(
            token in decision_language
            for token in (
                "keep",
                "hold",
                "reduce",
                "resize",
                "trim",
                "保留",
                "减持",
                "调整",
            )
        ):
            validation_codes.append("missing_existing_review_language")
        blocking_codes = tuple(
            code for code in validation_codes if code != "unknown_citation_removed"
        )
        if blocking_codes:
            audit.append(
                MarketCandidateAudit(
                    index=index,
                    symbol=symbol or None,
                    requested_mode=recommendation_mode or None,
                    expected_mode=expected_mode,
                    supplied_citation_ids=supplied_citation_ids,
                    accepted_citation_ids=citation_ids,
                    present_fields=tuple(key for key, value in fields.items() if value),
                    accepted=False,
                    validation_codes=tuple(validation_codes),
                )
            )
            continue
        if expected_mode != "new_exposure" and dca_suitable:
            dca_suitable = False
            fields["dca_guidance"] = (
                "not suitable for automatic DCA; this is a review or replacement "
                "candidate, not additive exposure"
            )
            validation_codes.append("dca_disabled_for_non_additive_mode")
        accepted.append(
            MarketWatchlistCandidate(
                symbol=symbol,
                name=str(candidate.name),
                category=str(candidate.candidate_category),
                citation_ids=citation_ids,
                dca_suitable=dca_suitable,
                recommendation_mode=recommendation_mode,
                **fields,
            )
        )
        audit.append(
            MarketCandidateAudit(
                index=index,
                symbol=symbol,
                requested_mode=recommendation_mode,
                expected_mode=expected_mode,
                supplied_citation_ids=supplied_citation_ids,
                accepted_citation_ids=citation_ids,
                present_fields=tuple(key for key, value in fields.items() if value),
                accepted=True,
                validation_codes=tuple(validation_codes) or ("accepted",),
            )
        )
    parse_status = "valid" if len(payload) <= 10 else "valid_truncated_for_audit"
    return clean_content, tuple(accepted), parse_status, len(payload), tuple(audit)
