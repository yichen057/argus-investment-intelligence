from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


SELECTION_ENGINE_DETERMINISTIC = "deterministic"
SELECTION_ENGINE_MODEL = "model"
SUPPORTED_SELECTION_ENGINES = {
    SELECTION_ENGINE_DETERMINISTIC,
    SELECTION_ENGINE_MODEL,
}
DETERMINISTIC_SELECTION_VERSION = "etf-fixed-rank-v1"
DETERMINISTIC_AUDITOR_VERSION = "etf-selection-auditor-v1"
MINIMUM_SELECTION_SCORE = 30.0
MAX_SELECTED_CANDIDATES = 3


_POSITIVE_SIGNALS = (
    "attractive",
    "breadth improved",
    "demand growth",
    "earnings growth",
    "earnings revisions rose",
    "expansion",
    "favorable",
    "improving",
    "leadership",
    "outperform",
    "recovery",
    "resilient",
    "tailwind",
    "upgrade",
)
_NEGATIVE_SIGNALS = (
    "concentration risk",
    "contraction",
    "decline",
    "downside",
    "elevated valuation",
    "headwind",
    "negative revisions",
    "overvalued",
    "slowdown",
    "underperform",
    "uncertainty",
    "weakening",
)
_PRIMARY_SOURCE_DOMAINS = (
    ".gov",
    "federalreserve.gov",
    "sec.gov",
    "spglobal.com",
    "msci.com",
    "ftserussell.com",
    "vanguard.com",
    "ishares.com",
    "ssga.com",
)


@dataclass(frozen=True)
class EtfSelectionDecision:
    symbol: str
    name: str
    category: str
    recommendation_mode: str
    citation_ids: tuple[str, ...]
    rank: int
    total_score: float
    score_components: tuple[tuple[str, float], ...]
    penalties: tuple[tuple[str, float], ...]
    market_signal_as_of: str
    rationale: str
    counter_evidence: str
    invalidation_signal: str
    overlap_risk: str
    dca_guidance: str
    dca_suitable: bool


@dataclass(frozen=True)
class EtfSelectionOutcome:
    index: int
    symbol: str
    expected_mode: str
    citation_ids: tuple[str, ...]
    eligible: bool
    selected: bool
    rank: int | None
    total_score: float
    score_components: tuple[tuple[str, float], ...]
    penalties: tuple[tuple[str, float], ...]
    market_signal_as_of: str | None
    validation_codes: tuple[str, ...]


@dataclass(frozen=True)
class EtfSelectionResult:
    decisions: tuple[EtfSelectionDecision, ...]
    outcomes: tuple[EtfSelectionOutcome, ...]
    version: str = DETERMINISTIC_SELECTION_VERSION


@dataclass(frozen=True)
class EtfSelectionAuditResult:
    status: str
    codes: tuple[str, ...]
    version: str = DETERMINISTIC_AUDITOR_VERSION


@dataclass(frozen=True)
class _ScoredCandidate:
    index: int
    candidate: Any
    symbol: str
    expected_mode: str
    citation_ids: tuple[str, ...]
    eligible: bool
    total_score: float
    score_components: tuple[tuple[str, float], ...]
    penalties: tuple[tuple[str, float], ...]
    market_signal_as_of: str | None
    validation_codes: tuple[str, ...]
    positive_count: int
    negative_count: int
    related_weight: float
    dca_profile_eligible: bool


def select_etf_candidates(
    *,
    candidates: tuple[Any, ...] | list[Any],
    positions: tuple[Any, ...] | list[Any],
    profile: Any | None,
    evidence_rows: list[dict[str, object]],
    generated_at: datetime,
) -> EtfSelectionResult:
    """Score a controlled ETF universe without asking a model to choose symbols.

    Only accepted Evidence-Gate passages are evaluated. Missing fee or liquidity
    evidence is a disclosed penalty, never replaced with stale hard-coded facts.
    """

    exact_holdings = {
        str(position.symbol).strip().upper(): position for position in positions
    }
    total_value = sum(
        max(0.0, float(getattr(position, "market_value", 0.0) or 0.0))
        for position in positions
    )
    exposure_counts: dict[str, int] = {}
    for candidate in candidates:
        exposure = _normalize(str(getattr(candidate, "exposure_key", "") or ""))
        if exposure:
            exposure_counts[exposure] = exposure_counts.get(exposure, 0) + 1

    scored = [
        _score_candidate(
            index=index,
            candidate=candidate,
            evidence_rows=evidence_rows,
            generated_at=generated_at,
            exact_holdings=exact_holdings,
            total_value=total_value,
            positions=positions,
            profile=profile,
            peer_count=exposure_counts.get(
                _normalize(str(getattr(candidate, "exposure_key", "") or "")), 1
            ),
        )
        for index, candidate in enumerate(candidates)
    ]

    eligible = [item for item in scored if item.eligible]
    eligible.sort(key=lambda item: (-item.total_score, item.symbol))
    selected: list[_ScoredCandidate] = []
    selected_exposures: set[str] = set()
    peer_rejected: set[str] = set()
    for item in eligible:
        exposure = _normalize(
            str(getattr(item.candidate, "exposure_key", "") or item.symbol)
        )
        if exposure in selected_exposures:
            peer_rejected.add(item.symbol)
            continue
        selected.append(item)
        selected_exposures.add(exposure)
        if len(selected) == MAX_SELECTED_CANDIDATES:
            break

    selected_ranks = {item.symbol: rank for rank, item in enumerate(selected, start=1)}
    outcomes: list[EtfSelectionOutcome] = []
    for item in scored:
        selected_rank = selected_ranks.get(item.symbol)
        codes = list(item.validation_codes)
        if item.symbol in peer_rejected:
            codes.append("lower_ranked_peer_same_exposure")
        elif item.eligible and selected_rank is None:
            codes.append("below_top_three_fixed_rank")
        elif selected_rank is not None:
            codes.append("selected_by_fixed_rank")
        outcomes.append(
            EtfSelectionOutcome(
                index=item.index,
                symbol=item.symbol,
                expected_mode=item.expected_mode,
                citation_ids=item.citation_ids,
                eligible=item.eligible,
                selected=selected_rank is not None,
                rank=selected_rank,
                total_score=item.total_score,
                score_components=item.score_components,
                penalties=item.penalties,
                market_signal_as_of=item.market_signal_as_of,
                validation_codes=tuple(dict.fromkeys(codes)),
            )
        )

    decisions = tuple(
        _decision_from_score(item, rank=selected_ranks[item.symbol], generated_at=generated_at)
        for item in selected
    )
    return EtfSelectionResult(decisions=decisions, outcomes=tuple(outcomes))


def audit_etf_selection(
    result: EtfSelectionResult,
    *,
    candidates: tuple[Any, ...] | list[Any],
    positions: tuple[Any, ...] | list[Any],
    allowed_citation_ids: set[str],
) -> EtfSelectionAuditResult:
    """Independently verify fixed-ranking invariants from structured inputs only."""

    codes: list[str] = []
    allowed_symbols = {
        str(candidate.symbol).strip().upper(): candidate for candidate in candidates
    }
    exact_holdings = {
        str(position.symbol).strip().upper() for position in positions
    }
    decisions = result.decisions
    symbols = [item.symbol for item in decisions]
    outcome_by_symbol = {item.symbol: item for item in result.outcomes}
    selected_outcome_symbols = {
        item.symbol for item in result.outcomes if item.selected
    }
    if set(symbols) != selected_outcome_symbols:
        codes.append("decision_outcome_selection_mismatch")
    if len(decisions) > MAX_SELECTED_CANDIDATES:
        codes.append("selection_limit_exceeded")
    if len(symbols) != len(set(symbols)):
        codes.append("duplicate_symbol")
    if [item.rank for item in decisions] != list(range(1, len(decisions) + 1)):
        codes.append("non_contiguous_rank")
    expected_order = sorted(decisions, key=lambda item: (-item.total_score, item.symbol))
    if list(decisions) != expected_order:
        codes.append("unstable_sort_order")
    for item in decisions:
        candidate = allowed_symbols.get(item.symbol)
        if candidate is None:
            codes.append(f"unknown_symbol:{item.symbol}")
            continue
        outcome = outcome_by_symbol.get(item.symbol)
        if outcome is None or not outcome.eligible:
            codes.append(f"ineligible_selected:{item.symbol}")
        elif (
            outcome.rank != item.rank
            or outcome.total_score != item.total_score
            or outcome.citation_ids != item.citation_ids
        ):
            codes.append(f"decision_outcome_value_mismatch:{item.symbol}")
        if item.total_score < MINIMUM_SELECTION_SCORE:
            codes.append(f"score_below_threshold:{item.symbol}")
        if not item.citation_ids or not set(item.citation_ids).issubset(
            allowed_citation_ids
        ):
            codes.append(f"invalid_citations:{item.symbol}")
        related = tuple(getattr(candidate, "related_holdings", ()) or ())
        expected_mode = (
            "existing_holding_review"
            if item.symbol in exact_holdings
            else "diversifying_replacement"
            if related
            else "new_exposure"
        )
        if item.recommendation_mode != expected_mode:
            codes.append(f"mode_mismatch:{item.symbol}")
        if expected_mode != "new_exposure" and item.dca_suitable:
            codes.append(f"unsafe_additive_dca:{item.symbol}")
    return EtfSelectionAuditResult(
        status="passed" if not codes else "failed",
        codes=tuple(codes) or ("all_invariants_passed",),
    )


def _score_candidate(
    *,
    index: int,
    candidate: Any,
    evidence_rows: list[dict[str, object]],
    generated_at: datetime,
    exact_holdings: dict[str, Any],
    total_value: float,
    positions: tuple[Any, ...] | list[Any],
    profile: Any | None,
    peer_count: int,
) -> _ScoredCandidate:
    symbol = str(candidate.symbol).strip().upper()
    related = tuple(getattr(candidate, "related_holdings", ()) or ())
    expected_mode = (
        "existing_holding_review"
        if symbol in exact_holdings
        else "diversifying_replacement"
        if related
        else "new_exposure"
    )
    matched_rows = [
        row
        for row in evidence_rows
        if _row_matches_candidate(row, candidate=candidate, peer_count=peer_count)
    ]
    citation_ids = tuple(
        dict.fromkeys(str(row.get("citation_id") or "") for row in matched_rows)
    )
    citation_ids = tuple(value for value in citation_ids if value)
    combined_text = " ".join(
        str(row.get("supported_passage") or row.get("text") or "")
        for row in matched_rows
    ).lower()
    positive_count = sum(combined_text.count(signal) for signal in _POSITIVE_SIGNALS)
    negative_count = sum(combined_text.count(signal) for signal in _NEGATIVE_SIGNALS)
    market_score = _clamp(10 + positive_count * 3 - negative_count * 2, 0, 25)

    domains = {
        _domain(str(row.get("source_uri") or ""))
        for row in matched_rows
        if _domain(str(row.get("source_uri") or ""))
    }
    has_primary = any(
        any(marker in domain for marker in _PRIMARY_SOURCE_DOMAINS)
        for domain in domains
    )
    has_publication_date = any(row.get("publication_date") for row in matched_rows)
    evidence_score = _clamp(
        6
        + len(citation_ids) * 3
        + len(domains) * 3
        + (3 if has_primary else 0)
        + (2 if has_publication_date else 0),
        0,
        25,
    )
    profile_score = _profile_fit_score(candidate, profile=profile)
    related_weight = _related_weight(
        candidate,
        positions=positions,
        exact_holdings=exact_holdings,
        total_value=total_value,
    )
    penalties = _candidate_penalties(
        candidate,
        text=combined_text,
        related_weight=related_weight,
        expected_mode=expected_mode,
    )
    total_score = round(
        profile_score + market_score + evidence_score - sum(value for _, value in penalties),
        2,
    )
    codes: list[str] = []
    if not str(getattr(candidate, "source_url", "") or "").startswith("https://"):
        codes.append("missing_verified_fund_reference")
    if not matched_rows:
        codes.append("no_candidate_specific_accepted_evidence")
    if peer_count > 1 and not matched_rows and any(
        _row_mentions_exposure(row, candidate=candidate) for row in evidence_rows
    ):
        codes.append("no_comparable_peer_specific_evidence")
    if not has_publication_date:
        codes.append("missing_publication_date_penalty")
    if "expense_ratio_missing" in dict(penalties):
        codes.append("missing_expense_ratio_penalty")
    if "liquidity_missing" in dict(penalties):
        codes.append("missing_liquidity_evidence_penalty")
    if total_score < MINIMUM_SELECTION_SCORE:
        codes.append("score_below_minimum")
    blocking = {
        "missing_verified_fund_reference",
        "no_candidate_specific_accepted_evidence",
        "no_comparable_peer_specific_evidence",
        "score_below_minimum",
    }
    eligible = not any(code in blocking for code in codes)
    market_signal_as_of = _latest_evidence_timestamp(matched_rows, generated_at)
    return _ScoredCandidate(
        index=index,
        candidate=candidate,
        symbol=symbol,
        expected_mode=expected_mode,
        citation_ids=citation_ids,
        eligible=eligible,
        total_score=total_score,
        score_components=(
            ("profile_holdings_fit", profile_score),
            ("timestamped_market_signal", market_score),
            ("evidence_quality", evidence_score),
        ),
        penalties=penalties,
        market_signal_as_of=market_signal_as_of,
        validation_codes=tuple(codes),
        positive_count=positive_count,
        negative_count=negative_count,
        related_weight=related_weight,
        dca_profile_eligible=_dca_profile_eligible(profile),
    )


def _decision_from_score(
    item: _ScoredCandidate,
    *,
    rank: int,
    generated_at: datetime,
) -> EtfSelectionDecision:
    candidate = item.candidate
    exposure = str(getattr(candidate, "exposure_key", "") or item.symbol)
    score_map = dict(item.score_components)
    if item.negative_count:
        counter = (
            f"Accepted passages contain {item.negative_count} downside or uncertainty "
            "signal(s); treat this as a research candidate, not a trade instruction."
        )
    else:
        counter = (
            "No explicit counter-signal was found in the accepted candidate-specific "
            "passages, so confidence is capped and another current source should be checked."
        )
    if item.expected_mode == "existing_holding_review":
        overlap = (
            f"{item.symbol} is already held. Review keep, reduce, or resize against the "
            "saved allocation policy; this is not a new-buy recommendation."
        )
    elif item.expected_mode == "diversifying_replacement":
        related = ", ".join(getattr(candidate, "related_holdings", ()) or ())
        overlap = (
            f"Related stocks already held: {related}. Use this ETF only as a possible "
            "replacement that reduces single-stock risk, not additive exposure."
        )
    else:
        overlap = (
            "No exact ETF or mapped direct-stock exposure was found, but broad funds may "
            "still contain this exposure; verify look-through overlap before acting."
        )
    risk = str(getattr(candidate, "candidate_category", ""))
    dca_suitable = (
        item.expected_mode == "new_exposure"
        and item.total_score >= 48
        and item.dca_profile_eligible
    )
    if risk == "industry_research" and item.total_score < 55:
        dca_suitable = False
    dca_guidance = (
        "eligible only for a bounded satellite DCA after the user sets a sector budget"
        if dca_suitable
        else "not suitable for automatic DCA"
    )
    return EtfSelectionDecision(
        symbol=item.symbol,
        name=str(candidate.name),
        category=str(candidate.candidate_category),
        recommendation_mode=item.expected_mode,
        citation_ids=item.citation_ids,
        rank=rank,
        total_score=item.total_score,
        score_components=item.score_components,
        penalties=item.penalties,
        market_signal_as_of=item.market_signal_as_of
        or generated_at.astimezone(timezone.utc).isoformat(),
        rationale=(
            f"Fixed rank #{rank}: {exposure} passed the eligibility gate with score "
            f"{item.total_score:.1f}; Profile/holdings fit {score_map['profile_holdings_fit']:.1f}, "
            f"market signal {score_map['timestamped_market_signal']:.1f}, and evidence "
            f"quality {score_map['evidence_quality']:.1f}."
        ),
        counter_evidence=counter,
        invalidation_signal=(
            "Re-run the fixed ranking when the evidence timestamp, Profile, or holdings "
            "change; invalidate this candidate if it fails eligibility or falls below the "
            f"{MINIMUM_SELECTION_SCORE:.0f}-point minimum."
        ),
        overlap_risk=overlap,
        dca_guidance=dca_guidance,
        dca_suitable=dca_suitable,
    )


def _row_matches_candidate(
    row: dict[str, object], *, candidate: Any, peer_count: int
) -> bool:
    if _row_mentions_symbol_or_name(row, candidate=candidate):
        return True
    if peer_count > 1:
        return False
    text = _normalize(_row_text(row))
    exposure = _normalize(str(getattr(candidate, "exposure_key", "") or ""))
    return bool(exposure and exposure in text)


def _row_mentions_symbol_or_name(row: dict[str, object], *, candidate: Any) -> bool:
    text = _row_text(row).lower()
    symbol = re.escape(str(candidate.symbol).strip())
    if re.search(rf"(?<![a-z0-9]){symbol}(?![a-z0-9])", text, flags=re.IGNORECASE):
        return True
    name_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", str(candidate.name).lower())
        if len(token) >= 5 and token not in {"fund", "index", "select", "sector"}
    ]
    return len(name_tokens) >= 2 and sum(token in text for token in name_tokens) >= 2


def _row_mentions_exposure(row: dict[str, object], *, candidate: Any) -> bool:
    exposure = _normalize(str(getattr(candidate, "exposure_key", "") or ""))
    return bool(exposure and exposure in _normalize(_row_text(row)))


def _row_text(row: dict[str, object]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "supported_passage", "text")
    )


def _profile_fit_score(candidate: Any, *, profile: Any | None) -> float:
    score = 12.0
    category = str(getattr(candidate, "candidate_category", ""))
    risk = str(getattr(profile, "risk_tolerance", "") or "").lower()
    horizon = str(getattr(profile, "investment_horizon", "") or "").lower()
    experience = str(getattr(profile, "investing_experience", "") or "").lower()
    liquidity = str(getattr(profile, "liquidity_needs", "") or "").lower()
    style = str(getattr(profile, "preferred_style", "") or "").lower()
    budget = float(
        getattr(profile, "monthly_sector_satellite_budget", 0.0) or 0.0
    )
    if any(value in horizon for value in ("10+", "long")):
        score += 4
    elif any(value in horizon for value in ("0-3", "short")):
        score -= 4
    if "aggressive" in risk:
        score += 4 if category == "industry_research" else 2
    elif "conservative" in risk:
        score -= 5 if category == "industry_research" else 2
    if "high" in liquidity:
        score -= 4
    elif "low" in liquidity:
        score += 2
    if category == "industry_research" and any(
        value in experience for value in ("none", "beginner", "<1", "0-1")
    ):
        score -= 3
    if "macro" in style:
        score += 2
    if "strategic" in style and category == "industry_research":
        score -= 2
    score += 3 if budget > 0 else -2
    return round(_clamp(score, 0, 25), 2)


def _dca_profile_eligible(profile: Any | None) -> bool:
    budget = float(
        getattr(profile, "monthly_sector_satellite_budget", 0.0) or 0.0
    )
    risk = str(getattr(profile, "risk_tolerance", "") or "").lower()
    horizon = str(getattr(profile, "investment_horizon", "") or "").lower()
    liquidity = str(getattr(profile, "liquidity_needs", "") or "").lower()
    return (
        budget > 0
        and "conservative" not in risk
        and not any(value in horizon for value in ("0-3", "short"))
        and "high" not in liquidity
    )


def _candidate_penalties(
    candidate: Any,
    *,
    text: str,
    related_weight: float,
    expected_mode: str,
) -> tuple[tuple[str, float], ...]:
    penalties: list[tuple[str, float]] = []
    if expected_mode == "existing_holding_review":
        penalties.append(("exact_holding_overlap", 2.0))
    if related_weight > 0:
        penalties.append(
            (
                "mapped_stock_concentration",
                round(min(15, related_weight * 30), 2),
            )
        )
    if str(getattr(candidate, "candidate_category", "")) == "industry_research":
        penalties.append(("narrow_industry_concentration", 4.0))
    else:
        penalties.append(("sector_concentration", 1.5))
    metric_text = _metric_context(text, str(candidate.symbol))
    expense = _extract_expense_ratio(metric_text)
    if expense is None:
        penalties.append(("expense_ratio_missing", 1.5))
    elif expense > 0.50:
        penalties.append(("expense_ratio_high", 5.0))
    elif expense > 0.25:
        penalties.append(("expense_ratio_moderate", 2.0))
    if not any(
        term in metric_text
        for term in (
            "liquid",
            "liquidity",
            "trading volume",
            "average volume",
            "assets under management",
            "aum",
        )
    ):
        penalties.append(("liquidity_missing", 1.5))
    elif any(
        term in metric_text for term in ("illiquid", "low liquidity", "thinly traded")
    ):
        penalties.append(("liquidity_risk", 6.0))
    return tuple(penalties)


def _extract_expense_ratio(text: str) -> float | None:
    patterns = (
        r"expense ratio[^%]{0,50}?([0-9]+(?:\.[0-9]+)?)\s*%",
        r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,35}?expense ratio",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _metric_context(text: str, symbol: str) -> str:
    """Keep fund metrics tied to the named ticker in comparison passages."""

    normalized_symbol = symbol.strip().lower()
    contexts: list[str] = []
    for match in re.finditer(
        rf"(?<![a-z0-9]){re.escape(normalized_symbol)}(?![a-z0-9])",
        text,
        flags=re.IGNORECASE,
    ):
        contexts.append(text[max(0, match.start() - 160) : match.end() + 240])
    return " ".join(contexts)


def _related_weight(
    candidate: Any,
    *,
    positions: tuple[Any, ...] | list[Any],
    exact_holdings: dict[str, Any],
    total_value: float,
) -> float:
    if total_value <= 0:
        return 0.0
    related = {
        str(value).strip().upper()
        for value in (getattr(candidate, "related_holdings", ()) or ())
    }
    symbol = str(candidate.symbol).strip().upper()
    symbols = related | ({symbol} if symbol in exact_holdings else set())
    value = sum(
        max(0.0, float(getattr(position, "market_value", 0.0) or 0.0))
        for position in positions
        if str(position.symbol).strip().upper() in symbols
    )
    return value / total_value


def _latest_evidence_timestamp(
    rows: list[dict[str, object]], generated_at: datetime
) -> str | None:
    values = [
        str(row.get("publication_date") or row.get("retrieved_at") or "")
        for row in rows
    ]
    values = [value for value in values if value]
    if values:
        return max(values)
    return generated_at.astimezone(timezone.utc).isoformat() if rows else None


def _domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
