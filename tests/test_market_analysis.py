from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from investment_agent.portfolio.market_analysis import (
    IndependentSearchMarketAnalysisService,
    MarketAnalysisError,
    _attach_verifiable_market_citations,
    _candidate_peer_comparison_symbols,
    _extract_watchlist,
    _normalize_known_citations,
    market_prompt,
    market_search_query,
)
from investment_agent.providers.types import Deployment, ModelResponse
from investment_agent.search import WebEvidence, WebSearchResponse


class FakeIndependentSearch:
    provider_name = "exa"

    def __init__(self, evidence: WebEvidence) -> None:
        self.evidence = evidence
        self.queries: list[str] = []
        self.excluded_domains: list[tuple[str, ...]] = []

    def search(
        self,
        query: str,
        *,
        as_of_date=None,
        exclude_domains: tuple[str, ...] = (),
    ) -> WebSearchResponse:
        assert as_of_date is None
        self.queries.append(query)
        self.excluded_domains.append(exclude_domains)
        return WebSearchResponse(
            provider="exa",
            query=query,
            request_id="search-1",
            search_type="auto",
            results=(self.evidence,),
            estimated_cost_usd=0.007,
        )


class FakeDiverseIndependentSearch:
    provider_name = "exa"

    def __init__(self, evidence: tuple[WebEvidence, WebEvidence]) -> None:
        self.evidence = evidence
        self.queries: list[str] = []
        self.excluded_domains: list[tuple[str, ...]] = []

    def search(
        self,
        query: str,
        *,
        as_of_date=None,
        exclude_domains: tuple[str, ...] = (),
    ) -> WebSearchResponse:
        assert as_of_date is None
        index = min(len(self.queries), len(self.evidence) - 1)
        self.queries.append(query)
        self.excluded_domains.append(exclude_domains)
        return WebSearchResponse(
            provider="exa",
            query=query,
            request_id=f"search-{index + 1}",
            search_type="auto",
            results=(self.evidence[index],),
            estimated_cost_usd=0.007,
        )


class FakeAnswerModel:
    provider_name = "deepseek"
    model_name = "deepseek-v4-flash"
    deployment = Deployment.CLOUD
    serving_engine = "test"

    def __init__(self, content: str) -> None:
        self.content = content
        self.requests = []

    def generate(self, request) -> ModelResponse:
        self.requests.append(request)
        assert (
            request.tool_results[0].output["search"]["evidence_gate"]["decision"]
            == "supported"
        )
        return ModelResponse(
            provider=self.provider_name,
            model=self.model_name,
            deployment=self.deployment,
            serving_engine=self.serving_engine,
            content=self.content,
            prompt_tokens=120,
            completion_tokens=80,
            estimated_cost_usd=0.00004,
        )


class FakeSequencedAnswerModel(FakeAnswerModel):
    def __init__(self, contents: tuple[str, ...]) -> None:
        super().__init__(contents[0])
        self.contents = contents

    def generate(self, request) -> ModelResponse:
        index = min(len(self.requests), len(self.contents) - 1)
        self.content = self.contents[index]
        return super().generate(request)


def _market_evidence() -> WebEvidence:
    retrieved_at = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    passage = (
        "Current market risks and drivers for VTI include interest rates, earnings "
        "growth, and changing equity valuations."
    )
    return WebEvidence(
        evidence_key="web-vti",
        title="Current VTI market outlook",
        url="https://example.com/vti-outlook",
        author="Example Research",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
        text=passage,
        highlights=(passage,),
        highlight_scores=(0.9,),
    )


def _second_market_evidence() -> WebEvidence:
    evidence = _market_evidence()
    return WebEvidence(
        evidence_key="web-vti-counter",
        title="Independent VTI market risk data",
        url="https://federalreserve.gov/vti-risk-data",
        author="Federal Reserve",
        published_at=evidence.published_at,
        retrieved_at=evidence.retrieved_at,
        text=(
            "Independent current market risk drivers and sector outlook for VTI equity "
            "include monetary policy, interest rates, earnings revisions, valuation "
            "breadth, and semiconductor demand uncertainty."
        ),
        highlights=(
            "Independent current market risk drivers and sector outlook for VTI equity "
            "include monetary policy, interest rates, earnings revisions, valuation "
            "breadth, and semiconductor demand uncertainty.",
        ),
        highlight_scores=(0.88,),
    )


def _concrete_driver_evidence_without_generic_gate_words() -> WebEvidence:
    retrieved_at = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
    passage = (
        "The Federal Reserve held interest rates steady while inflation expectations "
        "and earnings growth remained the main sources of uncertainty for U.S. equities."
    )
    return WebEvidence(
        evidence_key="web-concrete-driver",
        title="Federal Reserve and earnings context",
        url="https://federalreserve.gov/monetary-policy-context",
        author="Federal Reserve",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
        text=passage,
        highlights=(passage,),
        highlight_scores=(0.91,),
    )


def test_independent_market_analysis_uses_exa_then_selected_model() -> None:
    search = FakeIndependentSearch(_market_evidence())
    answer_model = FakeAnswerModel(
        "## Current context\n- Rates remain a driver. [source:W1]"
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=search,
        answer_provider=answer_model,
        max_search_calls=1,
    )

    result = service.analyze(
        "Explain the accepted evidence with citations.",
        search_query="current market risks drivers outlook VTI Equity",
    )

    assert result.provider == "deepseek"
    assert result.search_provider == "exa"
    assert result.search_calls == 1
    assert result.search_estimated_cost_usd == 0.007
    assert result.answer_model_estimated_cost_usd == 0.00004
    assert result.answer_model_calls == 1
    assert result.estimated_cost_usd == 0.00704
    assert result.sources[0].citation_id == "W1"
    assert answer_model.requests[0].role == "portfolio_market_analysis"


def test_market_gate_accepts_concrete_driver_without_literal_generic_label() -> None:
    answer_model = FakeAnswerModel(
        "## Current context\n- Rates and earnings are the accepted drivers. [source:W1]"
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=FakeIndependentSearch(
            _concrete_driver_evidence_without_generic_gate_words()
        ),
        answer_provider=answer_model,
        max_search_calls=1,
    )

    result = service.analyze(
        "Explain current conditions with citations.",
        search_query="current outlook GLD QQQ TSLA",
        evidence_gate_query="market risk drivers",
    )

    assert result.source_count == 1
    assert result.sources[0].citation_id == "W1"
    assert len(answer_model.requests) == 1


def test_independent_market_analysis_rejects_unknown_citation() -> None:
    service = IndependentSearchMarketAnalysisService(
        search_provider=FakeIndependentSearch(_market_evidence()),
        answer_provider=FakeAnswerModel("Unsupported claim. [source:W99]"),
        max_search_calls=1,
    )

    with pytest.raises(MarketAnalysisError) as exc_info:
        service.analyze(
            "Explain the accepted evidence with citations.",
            search_query="current market risks drivers outlook VTI Equity",
        )

    assert exc_info.value.code == "invalid_market_analysis_citations"


def test_market_analysis_allows_one_same_model_citation_repair() -> None:
    answer_model = FakeSequencedAnswerModel(
        (
            "First draft omitted its citation.",
            "## Repaired context\n- Rates remain a driver. [source:W1]",
        )
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=FakeIndependentSearch(_market_evidence()),
        answer_provider=answer_model,
        max_search_calls=1,
    )

    result = service.analyze(
        "Explain the accepted evidence with citations.",
        search_query="current market risks drivers outlook VTI Equity",
    )

    assert result.answer_model_calls == 2
    assert result.answer_model_estimated_cost_usd == 0.00008
    assert result.estimated_cost_usd == 0.00708
    assert result.prompt_tokens == 240
    assert result.completion_tokens == 160
    assert len(answer_model.requests) == 2
    assert answer_model.requests[1].role == "portfolio_market_analysis_citation_repair"
    assert "never combine IDs" in answer_model.requests[1].objective


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Combined [source:W1/W2]", "Combined [source:W1] [source:W2]"),
        ("Combined [Source: W1, W2]", "Combined [source:W1] [source:W2]"),
        ("Combined 【W1、W2】", "Combined [source:W1] [source:W2]"),
        ("Numeric footnote [1]", "Numeric footnote [source:W1]"),
        ("Markdown footnote [^2]", "Markdown footnote [source:W2]"),
    ],
)
def test_known_combined_citation_formats_are_normalized(
    content: str,
    expected: str,
) -> None:
    assert (
        _normalize_known_citations(
            content,
            allowed_citation_ids={"W1", "W2"},
        )
        == expected
    )


def test_unknown_combined_citation_is_not_normalized() -> None:
    content = "Combined [source:W1/W99]"

    assert (
        _normalize_known_citations(
            content,
            allowed_citation_ids={"W1", "W2"},
        )
        == content
    )


def test_local_market_citation_repair_requires_direct_term_overlap() -> None:
    content = (
        "## Current context\n"
        "Interest rates and earnings growth remain important equity uncertainties.\n"
        "A completely unrelated personalized trade instruction."
    )

    repaired = _attach_verifiable_market_citations(
        content,
        evidence_rows=[
            {
                "citation_id": "W1",
                "supported_passage": (
                    "Interest rates and earnings growth remained the main sources of "
                    "uncertainty for U.S. equities."
                ),
            }
        ],
    )

    assert "uncertainties. [source:W1]" in repaired
    assert "trade instruction. [source:" not in repaired


def test_portfolio_market_analysis_runs_two_facets_and_requests_diverse_domains() -> (
    None
):
    search = FakeDiverseIndependentSearch(
        (_market_evidence(), _second_market_evidence())
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=search,
        answer_provider=FakeAnswerModel(
            "## Current context\n- Rates remain a driver. [source:W1] [source:W2]"
        ),
        max_search_calls=2,
    )

    result = service.analyze(
        "Explain the accepted evidence with citations.",
        search_query="current market risks drivers outlook VTI Equity",
    )

    assert result.search_calls == 2
    assert result.search_estimated_cost_usd == 0.014
    assert result.source_count == 2
    assert result.domain_count == 2
    assert "counter evidence" in search.queries[1]
    assert search.excluded_domains[1] == ("example.com",)
    assert result.limitations == ()
    facet_gates = (
        service._answer_provider.requests[0]
        .tool_results[0]
        .output["search"]["facet_gates"]
    )
    assert facet_gates["sector_outlook"]["decision"] == "supported"


def test_peer_comparison_scope_uses_direct_stock_exposure_and_all_fund_peers() -> None:
    positions = [SimpleNamespace(symbol="AMZN", market_value=5000)]
    candidates = [
        SimpleNamespace(
            symbol="XLY",
            exposure_key="Consumer Discretionary",
            related_holdings=("AMZN",),
        ),
        SimpleNamespace(
            symbol="VCR",
            exposure_key="Consumer Discretionary",
            related_holdings=("AMZN",),
        ),
        SimpleNamespace(
            symbol="XLK",
            exposure_key="Technology",
            related_holdings=(),
        ),
    ]

    assert _candidate_peer_comparison_symbols(positions, candidates) == (
        "VCR",
        "XLY",
    )


def test_portfolio_market_analysis_allows_one_domain_with_visible_limitation() -> None:
    search = FakeIndependentSearch(_market_evidence())
    answer_model = FakeAnswerModel(
        "## Limited-source context\n- Rates remain a driver. [source:W1]"
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=search,
        answer_provider=answer_model,
        max_search_calls=2,
    )

    result = service.analyze(
        "Explain the accepted evidence with citations.",
        search_query="current market risks drivers outlook VTI Equity",
    )

    assert result.domain_count == 1
    assert result.limitations
    assert "one independent source domain" in result.limitations[0]
    assert len(answer_model.requests) == 1
    assert (
        "do not call the analysis comprehensive" in answer_model.requests[0].objective
    )


def test_market_analysis_extracts_validated_bounded_etf_watchlist() -> None:
    candidate = SimpleNamespace(
        symbol="SOXX",
        name="iShares Semiconductor ETF",
        candidate_category="industry_research",
    )
    answer_model = FakeAnswerModel(
        "## Current context\n- Semiconductor demand merits review. [source:W1]\n"
        "```argus-sector-watchlist\n"
        '[{"symbol":"SOXX","recommendation_mode":"new_exposure",'
        '"rationale":"Demand evidence supports research",'
        '"counter_evidence":"Valuation may compress",'
        '"invalidation_signal":"Earnings revisions turn negative",'
        '"overlap_risk":"Broad funds already hold chips",'
        '"dca_guidance":"not suitable for automatic DCA",'
        '"dca_suitable":false,'
        '"citation_ids":["W1"]}]\n```'
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=FakeIndependentSearch(_market_evidence()),
        answer_provider=answer_model,
        max_search_calls=1,
        research_candidates=[candidate],
        selection_engine="model",
    )

    result = service.analyze(
        "Explain the accepted evidence with citations.",
        search_query="current market risks drivers outlook VTI Equity",
    )

    assert "argus-sector-watchlist" not in result.content
    assert len(result.watchlist) == 1
    assert result.watchlist[0].symbol == "SOXX"
    assert result.watchlist[0].citation_ids == ("W1",)
    assert result.watchlist[0].dca_suitable is False
    assert result.watchlist[0].recommendation_mode == "new_exposure"


def test_deterministic_engine_keeps_fixed_candidate_when_model_omits_it() -> None:
    retrieved_at = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    passage = (
        "XBI biotechnology sector outlook includes resilient demand growth, positive "
        "earnings revisions, and liquid trading. Its expense ratio is 0.35%, while "
        "valuation risk and policy uncertainty remain counter-evidence."
    )
    evidence = WebEvidence(
        evidence_key="web-xbi",
        title="XBI biotechnology outlook and fund facts",
        url="https://sec.gov/research/xbi",
        author="Example",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
        text=passage,
        highlights=(passage,),
        highlight_scores=(0.94,),
    )
    candidate = SimpleNamespace(
        symbol="XBI",
        name="SPDR S&P Biotech ETF",
        candidate_category="industry_research",
        exposure_key="Biotechnology",
        related_holdings=(),
        source_url="https://issuer.example/xbi",
    )
    answer_model = FakeAnswerModel(
        "```argus-sector-watchlist\n[]\n```\n"
        "## Current context\n- Biotechnology has both demand support and risk. [source:W1]"
    )
    service = IndependentSearchMarketAnalysisService(
        search_provider=FakeIndependentSearch(evidence),
        answer_provider=answer_model,
        max_search_calls=1,
        research_candidates=[candidate],
        profile=SimpleNamespace(
            risk_tolerance="aggressive",
            investment_horizon="10+ years",
            investing_experience="3-7 years",
            liquidity_needs="low",
            preferred_style="macro",
            monthly_sector_satellite_budget=200,
        ),
        selection_engine="deterministic",
    )

    result = service.analyze(
        "Explain the accepted evidence with citations.",
        search_query="current biotechnology sector outlook earnings valuation XBI",
    )

    assert [item.symbol for item in result.watchlist] == ["XBI"]
    assert result.selection_engine == "deterministic"
    assert result.audit_status == "passed"
    assert result.candidate_parse_status.endswith("explanations_fallback")
    assert len(result.candidate_audit) == 1
    assert result.candidate_audit[0].accepted is True
    assert result.candidate_audit[0].selection_source == "deterministic"
    assert "fixed-ranked JSON" in answer_model.requests[0].objective


def test_watchlist_requires_replacement_mode_when_related_stocks_are_held() -> None:
    candidate = SimpleNamespace(
        symbol="XSD",
        name="SPDR S&P Semiconductor ETF",
        candidate_category="industry_research",
        related_holdings=("NVDA",),
    )
    common = (
        '"symbol":"XSD","rationale":"Broader semiconductor basket",'
        '"counter_evidence":"Semiconductor valuations are elevated",'
        '"invalidation_signal":"Earnings revisions turn negative",'
        '"overlap_risk":"NVDA is already held",'
        '"dca_guidance":"Use only as a replacement",'
        '"dca_suitable":true,"citation_ids":["W1"]'
    )

    _, rejected, rejected_status, rejected_count, rejected_audit = _extract_watchlist(
        f'```argus-sector-watchlist\n[{{{common},"recommendation_mode":"new_exposure"}}]\n```',
        research_candidates=[candidate],
        allowed_citation_ids={"W1"},
    )
    _, accepted, accepted_status, accepted_count, accepted_audit = _extract_watchlist(
        f'```argus-sector-watchlist\n[{{{common},"recommendation_mode":"diversifying_replacement"}}]\n```',
        research_candidates=[candidate],
        allowed_citation_ids={"W1"},
    )

    assert rejected == ()
    assert rejected_status == "valid"
    assert rejected_count == 1
    assert rejected_audit[0].accepted is False
    assert "recommendation_mode_conflict" in rejected_audit[0].validation_codes
    assert len(accepted) == 1
    assert accepted_status == "valid"
    assert accepted_count == 1
    assert accepted_audit[0].accepted is True
    assert accepted[0].recommendation_mode == "diversifying_replacement"
    assert accepted[0].dca_suitable is False
    assert "not additive exposure" in accepted[0].dca_guidance

    exact_common = common.replace(
        '"Use only as a replacement"',
        '"Review whether to keep, reduce, or resize"',
    )
    _, exact_holding_review, _, _, exact_audit = _extract_watchlist(
        f'```argus-sector-watchlist\n[{{{exact_common},"recommendation_mode":"existing_holding_review"}}]\n```',
        research_candidates=[candidate],
        allowed_citation_ids={"W1"},
        held_symbols={"XSD"},
    )
    assert len(exact_holding_review) == 1
    assert exact_holding_review[0].recommendation_mode == "existing_holding_review"
    assert exact_holding_review[0].dca_suitable is False
    assert exact_audit[0].validation_codes == ("dca_disabled_for_non_additive_mode",)


def test_watchlist_audit_records_structural_rejections_without_raw_output() -> None:
    candidate = SimpleNamespace(
        symbol="XLV",
        name="Health Care Select Sector SPDR Fund",
        candidate_category="sector_research",
        related_holdings=(),
    )

    clean, watchlist, parse_status, raw_count, audit = _extract_watchlist(
        """Readable answer.
```argus-sector-watchlist
[{"symbol":"XLV","recommendation_mode":"new_exposure","rationale":"Current thesis","citation_ids":["W9"]}]
```""",
        research_candidates=[candidate],
        allowed_citation_ids={"W1"},
    )

    assert clean == "Readable answer."
    assert watchlist == ()
    assert parse_status == "valid"
    assert raw_count == 1
    assert audit[0].symbol == "XLV"
    assert audit[0].accepted is False
    assert set(audit[0].validation_codes) == {
        "no_accepted_citation",
        "missing_required_fields",
        "invalid_dca_suitable",
    }


def test_market_prompt_and_search_query_send_no_dollar_values() -> None:
    positions = [
        SimpleNamespace(symbol="VTI", asset_class="Equity", market_value=9000),
        SimpleNamespace(symbol="BND", asset_class="Bond", market_value=1000),
    ]

    candidates = [
        SimpleNamespace(
            symbol="SOXX",
            name="iShares Semiconductor ETF",
            portfolio_role="Semiconductors industry research satellite",
        )
    ]
    prompt = market_prompt(
        positions,
        portfolio_as_of=date(2026, 7, 15).isoformat(),
        research_candidates=candidates,
        profile=SimpleNamespace(
            risk_tolerance="moderate",
            investment_horizon="10+ years",
            investing_experience="3-7 years",
            liquidity_needs="low",
            preferred_style="strategic_index",
            rebalance_preference="contributions_first",
        ),
    )
    search_query = market_search_query(positions)

    assert '"portfolio_weight": 0.9' in prompt
    assert '"portfolio_weight": 0.1' in prompt
    assert "VTI" in search_query
    assert "BND" in search_query
    assert "structured sector watchlist" in prompt
    assert "Before the readable analysis, output exactly one fenced" in prompt
    assert "Stay under 650 words" in prompt
    assert "fixed-ranked candidate list" in prompt
    assert "SOXX" in prompt
    assert '"exact_etf_held": false' in prompt
    assert "diversifying_replacement" in prompt
    assert "existing_holding_review" in prompt
    assert '"investment_horizon": "10+ years"' in prompt
    assert "not a trade instruction" in prompt
    assert "9000" not in prompt
    assert "9000" not in search_query
