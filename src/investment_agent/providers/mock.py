from __future__ import annotations

import csv
import math
import re
from io import StringIO
from typing import Any

from investment_agent.harness.types import ToolCall
from investment_agent.providers.types import Deployment, ModelRequest, ModelResponse
from investment_agent.retrieval.constants import RETRIEVE_EVIDENCE_TOOL

NO_EVIDENCE_ANSWER = "I could not find relevant local evidence for this question."


class DeterministicMockModelProvider:
    """Local deterministic model provider for agent-loop tests and demos."""

    provider_name = "local"
    model_name = "deterministic-mock-researcher"
    deployment = Deployment.LOCAL
    serving_engine = "python-mock"
    input_cost_per_million_usd = 0.0
    output_cost_per_million_usd = 0.0

    def __init__(self, *, retrieval_tool_name: str = RETRIEVE_EVIDENCE_TOOL) -> None:
        self._retrieval_tool_name = retrieval_tool_name

    def generate(self, request: ModelRequest) -> ModelResponse:
        prompt_tokens = _count_tokens(request.objective) + sum(
            _count_tokens(str(result.output)) for result in request.tool_results
        )
        if not request.tool_results:
            return ModelResponse(
                provider=self.provider_name,
                model=self.model_name,
                deployment=self.deployment,
                serving_engine=self.serving_engine,
                content="",
                prompt_tokens=prompt_tokens,
                completion_tokens=8,
                estimated_cost_usd=0.0,
                tool_call=ToolCall(
                    call_id=f"retrieve-{request.iteration + 1}",
                    name=self._retrieval_tool_name,
                    arguments={
                        "query": request.objective,
                        "top_k": 3,
                        "document_id": request.document_id,
                        "as_of_date": (
                            request.as_of_date.isoformat()
                            if request.as_of_date is not None
                            else None
                        ),
                    },
                ),
            )

        content = _answer_from_tool_result(
            request.tool_results[-1],
            query=request.objective,
        )
        return ModelResponse(
            provider=self.provider_name,
            model=self.model_name,
            deployment=self.deployment,
            serving_engine=self.serving_engine,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=_count_tokens(content),
            estimated_cost_usd=0.0,
        )


def _answer_from_tool_result(tool_result, *, query: str) -> str:
    if tool_result.status != "ok":
        return f"Unable to retrieve local evidence: {tool_result.error_code}."

    results = tool_result.output.get("results", [])
    if not results:
        return NO_EVIDENCE_ANSWER

    search = tool_result.output.get("search")
    gate = search.get("evidence_gate") if isinstance(search, dict) else None
    if isinstance(gate, dict):
        if gate.get("decision") != "supported":
            return NO_EVIDENCE_ANSWER
        passages = [
            passage.strip()
            for result in results[:3]
            if isinstance((passage := result.get("supported_passage")), str)
            and passage.strip()
        ]
        if passages:
            return "Based on the strongest local source, " + " ".join(passages)
        # A supported gate result without its accepted passage is an invalid
        # contract. Refuse instead of silently re-running a different evidence rule.
        return NO_EVIDENCE_ANSWER

    # Backward-compatible path for stored/legacy tool results created before the
    # unified Evidence Gate contract was introduced.
    for result in results:
        if result.get("source_type") == "csv":
            csv_answer = _answer_from_csv_result(result, query=query)
            if csv_answer is not None:
                return f"Based on the strongest local source, {csv_answer}"
            continue

        if not _result_covers_requested_years(result, query=query):
            continue

        context = str(result.get("context", ""))
        text = str(result.get("text", ""))
        passage = _supported_passage(
            context if len(context.strip()) > len(text.strip()) else text,
            query=query,
        )
        if passage is None and context.strip() and context != text:
            passage = _supported_passage(text, query=query)
        if passage is not None:
            return f"Based on the strongest local source, {passage}"
    return NO_EVIDENCE_ANSWER


def _answer_from_csv_result(result: dict[str, Any], *, query: str) -> str | None:
    if result.get("source_type") != "csv":
        return None
    text = str(result.get("text", ""))
    headers, records = _parse_csv_rows(text)
    if not headers or not records:
        return None
    if _is_investment_decision_question(query):
        return None

    time_column = headers[0]
    if not _csv_covers_requested_years(query, records=records, time_column=time_column):
        return None

    numeric_columns = [
        column
        for column in headers[1:]
        if any(_parse_number(record.get(column, "")) is not None for record in records)
    ]
    if not numeric_columns:
        return None

    if _is_factor_question(query):
        selected_columns = _select_factor_columns(numeric_columns)
    else:
        selected_columns = _select_summary_columns(numeric_columns, query=query)
    if not selected_columns:
        return None

    sentences = [
        _summarize_numeric_column(
            label=_humanize_column(column),
            unit=_unit_for_column(column),
            time_column=time_column,
            column=column,
            records=records,
        )
        for column in selected_columns
    ]
    usable_sentences = [sentence for sentence in sentences if sentence]
    if not usable_sentences:
        return None
    if _is_factor_question(query):
        factor_summary = "; ".join(
            sentence.rstrip(".") for sentence in usable_sentences
        )
        return (
            "the local CSV tracks possible gold-price factors: "
            + factor_summary
            + "."
        )
    return " ".join(usable_sentences)


def _parse_csv_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        reader = csv.DictReader(StringIO(text.strip()))
        if reader.fieldnames is None:
            return [], []
        return list(reader.fieldnames), [dict(row) for row in reader]
    except csv.Error:
        return [], []


def _select_summary_columns(columns: list[str], *, query: str) -> list[str]:
    query_terms = _query_terms(query)
    meaningful_terms = query_terms - _GENERIC_QUERY_TERMS
    if meaningful_terms:
        scored_columns = [
            (
                len(meaningful_terms & _column_terms(column)),
                index,
                column,
            )
            for index, column in enumerate(columns)
        ]
        max_score = max((score for score, _, _ in scored_columns), default=0)
        if max_score == 0:
            return []

        minimum_score = 2 if max_score >= 2 else 1
        selected = [
            (score, index, column)
            for score, index, column in scored_columns
            if score >= minimum_score
        ]
        return [
            column
            for _, _, column in sorted(
                selected,
                key=lambda item: item[1],
            )
        ][:4]

    return _default_summary_columns(columns)


def _default_summary_columns(columns: list[str]) -> list[str]:
    priority_terms = ("gold", "return", "value", "price", "yield", "flow", "demand")
    prioritized = [
        column
        for column in columns
        if any(term in column.lower() for term in priority_terms)
    ]
    return (prioritized or columns)[:4]


def _select_factor_columns(columns: list[str]) -> list[str]:
    candidates = [
        column
        for column in columns
        if _is_factor_column(column) and not _is_outcome_column(column)
    ]
    return candidates[:4]


def _is_factor_column(column: str) -> bool:
    terms = _column_terms(column)
    factor_terms = {
        "bank",
        "demand",
        "dollar",
        "etf",
        "flow",
        "inflation",
        "rate",
        "real",
        "reserve",
        "share",
        "usd",
        "yield",
    }
    return bool(terms & factor_terms)


def _is_outcome_column(column: str) -> bool:
    terms = _column_terms(column)
    return "gold" in terms and bool(terms & {"price", "return", "value"})


_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "based",
    "be",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "give",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "may",
    "me",
    "might",
    "of",
    "on",
    "or",
    "show",
    "tell",
    "the",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "would",
    "why",
    "with",
    "you",
}

_GENERIC_QUERY_TERMS = {
    "analysis",
    "article",
    "asset",
    "brief",
    "data",
    "dataset",
    "document",
    "file",
    "indicator",
    "invest",
    "investing",
    "investment",
    "market",
    "metric",
    "report",
    "source",
    "summarize",
    "summary",
    "trend",
    "value",
}

_TERM_NORMALIZATION = {
    "advises": "advice",
    "advised": "advice",
    "advising": "advice",
    "affecting": "affect",
    "affects": "affect",
    "allocates": "allocate",
    "allocated": "allocate",
    "allocating": "allocate",
    "assets": "asset",
    "banks": "bank",
    "buys": "buy",
    "buying": "buy",
    "datasets": "dataset",
    "documents": "document",
    "drivers": "driver",
    "drives": "drive",
    "driven": "drive",
    "driving": "drive",
    "files": "file",
    "flows": "flow",
    "factors": "factor",
    "declined": "fall",
    "declines": "fall",
    "declining": "fall",
    "dropped": "fall",
    "drops": "fall",
    "falling": "fall",
    "fell": "fall",
    "indicators": "indicator",
    "influenced": "influence",
    "influences": "influence",
    "influencing": "influence",
    "invested": "invest",
    "invests": "invest",
    "investments": "investment",
    "markets": "market",
    "metrics": "metric",
    "prices": "price",
    "recommends": "recommend",
    "recommended": "recommend",
    "recommending": "recommend",
    "reports": "report",
    "returns": "return",
    "sells": "sell",
    "selling": "sell",
    "sources": "source",
    "summaries": "summary",
    "trends": "trend",
    "values": "value",
    "yields": "yield",
}

_INVESTMENT_DECISION_TERMS = {
    "advice",
    "allocate",
    "buy",
    "hold",
    "invest",
    "recommend",
    "sell",
}

_CSV_METRIC_TERMS = {
    "bank",
    "demand",
    "earnings",
    "eps",
    "flow",
    "margin",
    "price",
    "rate",
    "real",
    "return",
    "revenue",
    "share",
    "valuation",
    "yield",
}


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in _normalized_terms(query)
        if term not in _STOPWORDS and not term.isdigit()
    }


def _column_terms(column: str) -> set[str]:
    return set(_normalized_terms(column))


def _is_investment_decision_question(query: str) -> bool:
    terms = set(_normalized_terms(query))
    return bool(terms & _INVESTMENT_DECISION_TERMS) and not bool(
        terms & _CSV_METRIC_TERMS
    )


def _is_factor_question(query: str) -> bool:
    terms = set(_normalized_terms(query))
    return bool(terms & {"affect", "driver", "drive", "factor", "influence"})


def _result_covers_requested_years(result: dict[str, Any], *, query: str) -> bool:
    requested_years = _requested_years(query)
    if not requested_years:
        return True
    text = " ".join(
        str(result.get(field, ""))
        for field in ("text", "context", "excerpt", "title", "source_uri")
    )
    evidence_years = set(_requested_years(text))
    return requested_years.issubset(evidence_years)


def _csv_covers_requested_years(
    query: str,
    *,
    records: list[dict[str, str]],
    time_column: str,
) -> bool:
    requested_years = _requested_years(query)
    if not requested_years:
        return True
    evidence_years = {
        year
        for record in records
        for year in _requested_years(str(record.get(time_column, "")))
    }
    return bool(evidence_years) and requested_years.issubset(evidence_years)


def _requested_years(value: str) -> set[int]:
    years = {
        int(match)
        for match in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", value)
    }
    years.update(
        2000 + int(short_year)
        for short_year in re.findall(r"\b[12]h\s*[’']?(\d{2})\b", value.lower())
    )
    return years


def _normalized_terms(value: str) -> list[str]:
    return [
        _TERM_NORMALIZATION.get(term, term)
        for term in re.findall(r"[a-z0-9]+", value.lower())
        if term
    ]


def _summarize_numeric_column(
    *,
    label: str,
    unit: str,
    time_column: str,
    column: str,
    records: list[dict[str, str]],
) -> str | None:
    points = [
        (
            str(record.get(time_column, "")).strip(),
            _parse_number(record.get(column, "")),
        )
        for record in records
    ]
    numeric_points = [(period, value) for period, value in points if value is not None]
    if len(numeric_points) < 2:
        return None

    first_period, first_value = numeric_points[0]
    last_period, last_value = numeric_points[-1]
    peak_period, peak_value = max(numeric_points, key=lambda item: item[1])
    trough_period, trough_value = min(numeric_points, key=lambda item: item[1])
    direction = "rose" if last_value > first_value else "fell" if last_value < first_value else "was unchanged"
    sentence = (
        f"{label} {direction} from {_format_value(first_value, unit)} in "
        f"{first_period} to {_format_value(last_value, unit)} in {last_period}"
    )
    if peak_period != last_period:
        sentence += f", with a peak of {_format_value(peak_value, unit)} in {peak_period}"
    if trough_period != first_period:
        sentence += f" and a low of {_format_value(trough_value, unit)} in {trough_period}"
    return sentence + "."


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().replace(",", "").replace("%", "").replace("$", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _unit_for_column(column: str) -> str:
    lowered = column.lower()
    if lowered.endswith("_pct") or "pct" in lowered or "percent" in lowered:
        return "%"
    if lowered.endswith("_b") or "_b_" in lowered:
        return "$B"
    if lowered.endswith("_m") or "_m_" in lowered:
        return "$M"
    return ""


def _humanize_column(column: str) -> str:
    acronyms = {"etf": "ETF", "usd": "USD"}
    words = [
        word
        for word in column.replace("-", "_").split("_")
        if word and word.lower() not in {"pct", "b", "m"}
    ]
    rendered_words = [
        acronyms.get(word.lower(), word.title())
        for word in words
    ]
    return " ".join(rendered_words).strip() or column


def _format_value(value: float, unit: str) -> str:
    if value.is_integer():
        rendered = str(int(value))
    else:
        rendered = f"{value:.1f}".rstrip("0").rstrip(".")
    if unit == "%":
        return f"{rendered}%"
    if unit == "$B":
        return f"-${abs(value):g}B" if value < 0 else f"${rendered}B"
    if unit == "$M":
        return f"-${abs(value):g}M" if value < 0 else f"${rendered}M"
    return rendered


def _supported_passage(text: str, *, query: str) -> str | None:
    query_terms = _query_terms(query) - _GENERIC_QUERY_TERMS
    cleaned_lines = [
        line
        for raw_line in text.splitlines()
        if (line := _clean_markdown_line(raw_line))
    ]
    joined_text = " ".join(cleaned_lines)
    passages = re.split(r"(?<=[.!?])\s+", joined_text)
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for order, raw_passage in enumerate(passages):
        passage = " ".join(raw_passage.split()).strip()
        if not passage or passage in seen:
            continue
        seen.add(passage)
        if len(passage) < 20:
            continue
        if _looks_like_section_heading(passage):
            continue
        overlap = len(query_terms & _query_terms(passage))
        completed = _complete_sentence(passage)
        if not completed or _looks_incomplete_passage(completed):
            continue
        candidates.append((overlap, -order, completed))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    overlap, _, passage = candidates[0]
    cjk_passage = bool(re.search(r"[\u3400-\u9fff]", passage))
    required_overlap = (
        0
        if not query_terms or (cjk_passage and _requested_years(query))
        else min(4, max(2, math.ceil(len(query_terms) * 0.6)))
    )
    if overlap < required_overlap:
        return None

    selected = [passage]
    selected_terms = _query_terms(passage)
    ranked_neighbors = sorted(
        (
            candidate
            for candidate in candidates
            if candidate[2] != passage
            and candidate[0] >= min(1, required_overlap)
            and len(selected_terms & _query_terms(candidate[2])) >= 1
        ),
        reverse=True,
    )
    for _, _, neighbor in ranked_neighbors:
        combined = " ".join((*selected, neighbor))
        if len(combined) > 600:
            continue
        selected.append(neighbor)
        break
    return " ".join(selected)


def _clean_markdown_line(value: str) -> str:
    line = value.strip()
    if not line or line.startswith(("```", "---", "===", "┌", "│", "└")):
        return ""
    if re.fullmatch(r"\d{1,3}", line):
        return ""
    if re.match(r"^source\s*:", line, flags=re.IGNORECASE):
        return ""
    was_heading = bool(re.match(r"^#{1,6}\s+", line))
    line = re.sub(r"^#{1,6}\s+", "", line)
    if was_heading:
        parts = line.split()
        for index, token in enumerate(parts[1:], start=1):
            if token[:1].islower():
                line = " ".join(parts[max(0, index - 1) :])
                break
    line = re.sub(r"^[-*+]\s+", "", line)
    if line.startswith("|") and line.endswith("|"):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            return ""
        line = "; ".join(cell for cell in cells if cell)
    line = line.replace("**", "").replace("`", "")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _looks_like_section_heading(value: str) -> bool:
    collapsed = " ".join(value.split()).strip()
    words = re.findall(r"[A-Za-z0-9'’-]+", collapsed)
    return len(words) <= 12 and bool(
        re.match(
            r"^(?:\d+\s+)?(?:why|what|how|when|where|who|which|can|could|should|"
            r"does|do|is|are)\b.*\?$",
            collapsed,
            flags=re.IGNORECASE,
        )
    )


def _complete_sentence(value: str, *, limit: int = 600) -> str:
    value = value.strip()
    if len(value) > limit:
        sentence_end = max(
            value.rfind(".", 0, limit),
            value.rfind("?", 0, limit),
            value.rfind("!", 0, limit),
        )
        if sentence_end >= 20:
            value = value[: sentence_end + 1]
        else:
            return ""
    if value and value[-1] not in ".!?":
        value += "."
    return value


def _looks_incomplete_passage(value: str) -> bool:
    collapsed = " ".join(value.split()).strip()
    if collapsed.endswith("..."):
        return True
    return bool(
        re.search(
            r"\b(and|or|but|because|although|while|with|without|to|of|for|from|"
            r"by|in|on|at|as)[\s,;:.!?-]*$",
            collapsed,
            flags=re.IGNORECASE,
        )
    )


def _count_tokens(value: str | dict[str, Any]) -> int:
    if isinstance(value, dict):
        value = str(value)
    return max(1, len(value.split()))
