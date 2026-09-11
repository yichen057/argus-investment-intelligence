from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from html import escape
from io import StringIO
from typing import Any

from investment_agent.harness.agent_loop import AgentLoopResult
from investment_agent.research.claims import GeneratedClaim
from investment_agent.research.critic import CriticReview
from investment_agent.style_packs import StylePackDefinition


@dataclass(frozen=True)
class GeneratedReport:
    title: str
    report_type: str
    status: str
    report_json: dict[str, Any]
    rendered_html: str


def build_research_report(
    *,
    topic: str,
    question: str,
    agent_result: AgentLoopResult,
    claims: tuple[GeneratedClaim, ...],
    critic: CriticReview,
    style_pack: StylePackDefinition | None = None,
) -> GeneratedReport:
    clean_topic = _clean_report_topic(topic)
    title = f"{clean_topic} Research Brief"
    status = _report_status(agent_result, claims, critic)
    evidence = [
        {
            "evidence_id": source.evidence_id,
            "source_name": source.display_name,
            "source_uri": source.source_uri,
            "source_type": source.source_type,
            "title": source.title,
            "page_or_section": source.page_or_section,
            "excerpt": _normalize_evidence_excerpt(
                source.excerpt,
                source_type=source.source_type,
            ),
        }
        for source in agent_result.sources
    ]
    claim_items = [
        {
            "claim_key": claim.claim_key,
            "claim_text": claim.claim_text,
            "citation_ids": list(claim.citation_ids),
            "evidence_ids": list(claim.evidence_ids),
            "relations": claim.relations,
            "confidence": claim.confidence,
            "source_names": list(claim.source_names),
            "verification": {
                "status": claim.verification.status,
                "findings": list(claim.verification.findings),
                "term_overlap": claim.verification.term_overlap,
            },
        }
        for claim in claims
    ]
    critic_payload = {
        "status": critic.status,
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity,
                "message": finding.message,
            }
            for finding in critic.findings
        ],
    }
    chart_focus_text = " ".join(
        [
            question,
            agent_result.answer,
            *(claim.claim_text for claim in claims),
        ]
    )
    charts = _build_report_charts(evidence, focus_text=chart_focus_text)
    sections = _sections(
        question=question,
        answer=agent_result.answer,
        claims=claim_items,
        evidence=evidence,
        charts=charts,
        critic=critic_payload,
    )
    if style_pack is not None:
        sections = _order_sections(sections, style_pack=style_pack)
    report_json: dict[str, Any] = {
        "schema_version": "research-report-v1",
        "topic": clean_topic,
        "question": question.strip(),
        "run_id": agent_result.run_id,
        "run_key": agent_result.run_key,
        "answer": agent_result.answer,
        "claims": claim_items,
        "evidence": evidence,
        "charts": charts,
        "sections": sections,
        "critic": critic_payload,
        "metrics": {
            "iterations": agent_result.iterations,
            "total_tokens": agent_result.total_tokens,
            "total_estimated_cost_usd": agent_result.total_estimated_cost_usd,
        },
        "style_pack": _style_pack_payload(style_pack),
    }
    return GeneratedReport(
        title=title,
        report_type="research_brief",
        status=status,
        report_json=report_json,
        rendered_html=render_report_html(title=title, report_json=report_json),
    )


def build_web_research_report(
    *,
    topic: str,
    question: str,
    run_id: int,
    run_key: str,
    answer: str,
    web_sources: list[dict[str, Any]],
    grounding_method: str,
    evidence_scope: str,
    total_tokens: int,
    total_estimated_cost_usd: float,
    iterations: int,
    style_pack: StylePackDefinition,
) -> GeneratedReport:
    clean_topic = _clean_report_topic(topic)
    title = f"{clean_topic} Research Brief"
    sections = _order_sections(
        _web_answer_sections(
            answer,
            question=question,
            grounding_method=grounding_method,
            evidence_scope=evidence_scope,
        ),
        style_pack=style_pack,
    )
    report_json: dict[str, Any] = {
        "schema_version": "web-research-report-v1",
        "topic": clean_topic,
        "question": question.strip(),
        "run_id": run_id,
        "run_key": run_key,
        "answer": answer,
        "claims": [],
        "evidence": [],
        "web_sources": web_sources,
        "charts": [],
        "sections": sections,
        "critic": {
            "status": "web_evidence_validated",
            "findings": [],
        },
        "metrics": {
            "iterations": iterations,
            "source_ask_tokens": total_tokens,
            "source_ask_estimated_cost_usd": total_estimated_cost_usd,
            "report_generation_provider_tokens": 0,
            "report_generation_estimated_cost_usd": 0.0,
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": total_estimated_cost_usd,
        },
        "grounding_method": grounding_method,
        "evidence_scope": evidence_scope,
        "style_pack": _style_pack_payload(style_pack),
    }
    return GeneratedReport(
        title=title,
        report_type="web_research_brief",
        status="complete",
        report_json=report_json,
        rendered_html=render_report_html(title=title, report_json=report_json),
    )


def _style_pack_payload(
    style_pack: StylePackDefinition | None,
) -> dict[str, Any] | None:
    if style_pack is None:
        return None
    return {
        "id": style_pack.id,
        "name": style_pack.name,
        "research_lenses": list(style_pack.research_lenses),
        "portfolio_priorities": list(style_pack.portfolio_priorities),
        "references": [
            reference.model_dump(mode="json") for reference in style_pack.references
        ],
    }


def _web_answer_sections(
    answer: str,
    *,
    question: str,
    grounding_method: str,
    evidence_scope: str,
) -> list[dict[str, Any]]:
    heading_map = {
        "direct answer": "Executive Summary",
        "mechanism and drivers": "Key Claims",
        "supporting evidence": "Supporting Evidence",
        "risks and uncertainties": "Risks and Uncertainties",
        "counter-evidence and gaps": "Counter-Evidence and Gaps",
        "falsification conditions": "Falsification Conditions",
        "investment implications": "Investment Implications",
        "what to verify next": "Critic Review",
    }
    parsed: dict[str, list[str]] = {}
    active_heading: str | None = None
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        heading_match = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if heading_match is not None:
            normalized = heading_match.group(1).strip().lower().rstrip(":")
            active_heading = heading_map.get(normalized)
            if active_heading is not None:
                parsed.setdefault(active_heading, [])
            continue
        if line and active_heading is not None:
            parsed[active_heading].append(line)

    if parsed:
        sections = [
            {
                "heading": heading,
                "body": "\n".join(lines),
                "evidence_ids": [],
            }
            for heading, lines in parsed.items()
            if lines
        ]
    else:
        sentences = _split_web_answer_sentences(_plain_model_text(answer))
        summary = sentences[0] if sentences else _plain_model_text(answer)
        remaining = sentences[1:]
        counter_evidence = [
            sentence
            for sentence in remaining
            if _sentence_matches(
                sentence,
                "however",
                "despite",
                "weakened",
                "decoupling",
                "deviation",
                "but ",
            )
        ]
        implications = [
            sentence
            for sentence in remaining
            if sentence not in counter_evidence
            and sentence.lower().startswith(
                ("current evidence", "overall", "therefore")
            )
        ]
        mechanisms = [
            sentence
            for sentence in remaining
            if sentence not in counter_evidence
            and sentence not in implications
            and _sentence_matches(
                sentence,
                "mechanism",
                "channel",
                "attributed to",
                "because",
            )
        ]
        categorized = {*mechanisms, *counter_evidence, *implications}
        supporting = [sentence for sentence in remaining if sentence not in categorized]
        sections = [
            {
                "heading": "Executive Summary",
                "body": summary,
                "evidence_ids": [],
            }
        ]
        for heading, grouped_sentences in (
            ("Key Claims", mechanisms),
            ("Supporting Evidence", supporting),
            ("Counter-Evidence and Gaps", counter_evidence),
            ("Investment Implications", implications),
        ):
            if not grouped_sentences:
                continue
            sections.append(
                {
                    "heading": heading,
                    "body": "\n".join(
                        f"- {sentence}" for sentence in grouped_sentences
                    ),
                    "evidence_ids": [],
                }
            )

    present = {str(section["heading"]) for section in sections}
    if "Investment Implications" not in present:
        sections.append(
            {
                "heading": "Investment Implications",
                "body": (
                    f"Decision focus: {question.strip()}\n"
                    "Use this report as decision support, not a personalized instruction "
                    "to buy, sell, or size a position."
                ),
                "evidence_ids": [],
            }
        )
    sections.append(
        {
            "heading": "Research Provenance",
            "body": (
                f"Grounding method: {grounding_method}. Evidence scope: {evidence_scope}. "
                "Exa returned direct URLs and extractive passages; Argus applied its "
                "deterministic Evidence Gate before the selected answer model ran."
            ),
            "evidence_ids": [],
        }
    )
    return sections


def _split_web_answer_sentences(value: str) -> list[str]:
    abbreviations = re.compile(r"\b(?:U\.S|U\.K|e\.g|i\.e)\.", re.IGNORECASE)
    protected = abbreviations.sub(lambda match: match.group(0).replace(".", "∯"), value)
    return [
        sentence.strip().replace("∯", ".")
        for sentence in _SENTENCE_SPLIT_PATTERN.split(protected)
        if sentence.strip()
    ]


def _sentence_matches(sentence: str, *markers: str) -> bool:
    normalized = sentence.lower()
    return any(marker in normalized for marker in markers)


def _order_sections(
    sections: list[dict[str, Any]],
    *,
    style_pack: StylePackDefinition,
) -> list[dict[str, Any]]:
    section_keys = {
        "executive_summary": "Executive Summary",
        "thesis": "Investment Thesis",
        "drivers": "Key Claims",
        "valuation": "Supporting Evidence",
        "quality": "Supporting Evidence",
        "risks": "Risks and Uncertainties",
        "counter_evidence": "Counter-Evidence and Gaps",
        "falsification": "Falsification Conditions",
        "portfolio_implications": "Investment Implications",
        "next_checks": "Critic Review",
    }
    by_heading = {str(section.get("heading")): section for section in sections}
    ordered: list[dict[str, Any]] = []
    for key in style_pack.report_section_order:
        section = by_heading.get(section_keys[key])
        if section is not None and section not in ordered:
            ordered.append(section)
    ordered.extend(section for section in sections if section not in ordered)
    return ordered


def _clean_report_topic(topic: str) -> str:
    cleaned = " ".join(topic.strip().split())
    cleaned = re.sub(
        r"^(based on (this|the) (article|document|report|file),?\s*)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(please\s+)?(tell me|explain|summarize)\s+(about\s+)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(can|could|should)\s+i\s+"
        r"(invest\s+(in\s+)?|buy\s+|sell\s+|hold\s+|allocate\s+(to\s+)?)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(what\s+(is|are|was|were)|how\s+(did|does|do|has|have|is|are)|"
        r"why\s+(did|does|do|is|are)|can|could|should|does|do|is|are)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(in|for)\s+(20\d{2})\b", r"\2", cleaned, flags=re.IGNORECASE)
    return cleaned.strip() or "Research"


def render_report_html(*, title: str, report_json: dict[str, Any]) -> str:
    sections = report_json.get("sections", [])
    section_html = "\n".join(
        _render_section(section) for section in sections if isinstance(section, dict)
    )
    chart_html = _render_charts(report_json.get("charts", []))
    evidence_html = _render_evidence(report_json.get("evidence", []))
    web_sources_html = _render_web_sources(report_json.get("web_sources", []))
    metrics = report_json.get("metrics", {})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      color: #1f2933;
      background: #f5f7f8;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      padding: 32px;
    }}
    main {{
      max-width: 880px;
      margin: 0 auto;
      border: 1px solid #d9e0e6;
      border-radius: 8px;
      background: #ffffff;
      padding: 36px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 2rem;
      line-height: 1.15;
    }}
    h2 {{
      margin: 28px 0 10px;
      font-size: 1.15rem;
    }}
    p, li {{
      color: #4c5963;
      line-height: 1.65;
    }}
    .meta, .citation {{
      color: #64727f;
      font-size: 0.88rem;
    }}
    .section {{
      border-top: 1px solid #e1e7ec;
      padding-top: 4px;
    }}
    .evidence-list {{
      display: grid;
      gap: 12px;
      padding: 0;
      list-style: none;
    }}
    .evidence-list li {{
      border: 1px solid #d3dde5;
      border-radius: 8px;
      padding: 12px;
      background: #f8fafb;
    }}
    .chart-grid {{
      display: grid;
      gap: 14px;
      margin-top: 12px;
    }}
    .chart-card {{
      border: 1px solid #d3dde5;
      border-radius: 8px;
      padding: 16px;
      background: #fbfcfd;
    }}
    .chart-card h3 {{
      margin: 0 0 4px;
      font-size: 1rem;
    }}
    .chart-card .subtitle {{
      margin: 0 0 14px;
      color: #64727f;
      font-size: 0.88rem;
    }}
    .chart-insight {{
      margin: -2px 0 14px;
      border-left: 3px solid #2f7d62;
      padding-left: 12px;
      color: #33424f;
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .chart-row {{
      display: grid;
      grid-template-columns: minmax(150px, 1fr) minmax(220px, 2fr) 72px;
      gap: 12px;
      align-items: center;
      margin: 10px 0;
    }}
    .chart-label {{
      color: #34414c;
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .chart-track {{
      height: 14px;
      overflow: hidden;
      border-radius: 999px;
      background: #e7edf2;
    }}
    .chart-fill {{
      display: block;
      height: 100%;
      min-width: 3px;
      border-radius: inherit;
      background: #2f7d62;
    }}
    .chart-fill.negative {{
      background: #c2415d;
    }}
    .chart-value {{
      color: #1f2933;
      font-weight: 800;
      text-align: right;
    }}
    .chart-source {{
      grid-column: 1 / -1;
      margin-top: -6px;
      color: #64727f;
      font-size: 0.8rem;
    }}
    .chart-svg {{
      width: 100%;
      height: auto;
      margin-top: 8px;
      overflow: visible;
    }}
    .chart-axis {{
      stroke: #c8d3dc;
      stroke-width: 1;
    }}
    .chart-gridline {{
      stroke: #e7edf2;
      stroke-width: 1;
    }}
    .chart-axis-label {{
      fill: #64727f;
      font-size: 0.78rem;
    }}
    .svg-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 16px;
      margin: 12px 0 0;
      padding: 0;
      list-style: none;
    }}
    .svg-legend li {{
      display: flex;
      gap: 6px;
      align-items: center;
      margin: 0;
      color: #34414c;
      font-size: 0.88rem;
      line-height: 1.2;
    }}
    .legend-swatch {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex: 0 0 auto;
    }}
    .chart-source-line {{
      margin: 12px 0 0;
      color: #64727f;
      font-size: 0.82rem;
    }}
    @media (max-width: 720px) {{
      body {{
        padding: 16px;
      }}
      main {{
        padding: 24px;
      }}
      .chart-row {{
        grid-template-columns: 1fr;
        gap: 6px;
      }}
      .chart-value {{
        text-align: left;
      }}
      .chart-source {{
        margin-top: 0;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <p class="meta">Run {escape(str(report_json.get("run_id", "")))} · {escape(str(report_json.get("topic", "")))}</p>
    {chart_html}
    {section_html}
    {evidence_html}
    {web_sources_html}
    <section class="section">
      <h2>Source Ask Cost and Report Cost</h2>
      <p>Source Ask: {escape(str(metrics.get("iterations", 0)))} agent steps · {escape(str(metrics.get("source_ask_tokens", metrics.get("total_tokens", 0))))} provider-token estimate · ${float(metrics.get("source_ask_estimated_cost_usd", metrics.get("total_estimated_cost_usd", 0.0))):.4f} estimated provider cost</p>
      <p>HTML report generation: {escape(str(metrics.get("report_generation_provider_tokens", 0)))} provider tokens · ${float(metrics.get("report_generation_estimated_cost_usd", 0.0)):.4f} additional model cost.</p>
      <p class="meta">This report deterministically reorganizes the saved Ask result and does not call the model again. Actual provider billing is not returned per request.</p>
    </section>
  </main>
</body>
</html>"""


def _render_web_sources(web_sources: Any) -> str:
    if not isinstance(web_sources, list) or not web_sources:
        return ""
    items: list[str] = []
    for source in web_sources:
        if not isinstance(source, dict):
            continue
        title = escape(str(source.get("title") or source.get("url") or "Web source"))
        url = escape(str(source.get("url") or ""), quote=True)
        retrieved_at = escape(str(source.get("retrieved_at") or ""))
        citation_id = escape(str(source.get("citation_id") or ""))
        excerpt = escape(str(source.get("excerpt") or ""))
        if not url:
            continue
        items.append(
            f'<li><a href="{url}" target="_blank" rel="noreferrer">'
            f"{citation_id} {title}</a>"
            f'<p>{excerpt}</p><p class="meta">Retrieved {retrieved_at}</p></li>'
        )
    if not items:
        return ""
    return (
        '<section class="section"><h2>Argus-validated Web Evidence</h2>'
        '<ul class="evidence-list">' + "".join(items) + "</ul></section>"
    )


def _report_status(
    agent_result: AgentLoopResult,
    claims: tuple[GeneratedClaim, ...],
    critic: CriticReview,
) -> str:
    if agent_result.status != "complete":
        return agent_result.status
    if critic.status == "failed":
        return "needs_review"
    if not claims:
        return "insufficient_evidence"
    return "complete"


_PERCENT_PATTERN = re.compile(r"(?P<value>-?\d+(?:\.\d+)?)\s*%")
_MONEY_PATTERN = re.compile(r"\$(?P<value>-?\d[\d,]*(?:\.\d+)?)(?P<scale>[kKmMbB])?\b")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_TRAILING_LABEL_WORDS = {
    "at",
    "by",
    "declined",
    "expanded",
    "fell",
    "from",
    "improved",
    "increased",
    "is",
    "reached",
    "rose",
    "stood",
    "to",
    "totaled",
    "was",
    "were",
}


def _build_report_charts(
    evidence: list[dict[str, Any]],
    *,
    focus_text: str,
) -> list[dict[str, Any]]:
    focus_terms = _focus_terms(focus_text)
    charts = _extract_dataset_charts(evidence, focus_terms=focus_terms)
    percent_points = _extract_percent_points(evidence)
    money_points = _extract_money_points(evidence)
    if percent_points:
        charts.append(
            {
                "chart_id": "cited-percent-indicators",
                "title": "Cited Percent Indicators",
                "subtitle": (
                    "Percent values extracted from cited local evidence; use "
                    "these as source-backed indicators, not live market data."
                ),
                "chart_type": "bar",
                "unit": "%",
                "data": percent_points[:6],
            }
        )
    if money_points:
        charts.append(
            {
                "chart_id": "cited-currency-indicators",
                "title": "Cited Currency Indicators",
                "subtitle": (
                    "Dollar values extracted from cited local evidence and "
                    "normalized to USD millions when source text uses K/M/B."
                ),
                "chart_type": "bar",
                "unit": "$M",
                "data": money_points[:6],
            }
        )
    for chart in charts:
        narrative = _chart_narrative(chart)
        if narrative:
            chart["narrative"] = narrative
    return charts


def _extract_dataset_charts(
    evidence: list[dict[str, Any]],
    *,
    focus_terms: set[str],
) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    for item in evidence:
        if item.get("source_type") != "csv":
            continue
        rows = _parse_csv_rows(str(item.get("excerpt", "")))
        if len(rows) < 2:
            continue
        x_axis = _dataset_x_axis(rows)
        series = _dataset_numeric_series(rows, x_axis=x_axis)
        series = _filter_series_for_focus(series, focus_terms=focus_terms)
        if not series:
            continue

        source_name = str(item.get("source_name", "dataset"))
        evidence_id = int(item.get("evidence_id", 0) or 0)
        x_values = [str(row.get(x_axis, "")).strip() for row in rows[:8]]
        percent_series = [item for item in series if item["unit"] == "%"][:4]
        currency_series = [
            item for item in series if str(item["unit"]).startswith("$")
        ][:2]
        numeric_series = [item for item in series if item["unit"] == ""][:3]

        if percent_series:
            charts.append(
                {
                    "chart_id": f"dataset-percent-trend-{evidence_id}",
                    "title": f"Percent Trend: {source_name}",
                    "subtitle": (
                        f"Time-series indicators parsed from cited CSV evidence "
                        f"using {x_axis} as the x-axis."
                    ),
                    "chart_type": "line",
                    "x_axis": x_axis,
                    "x_values": x_values,
                    "series": _trim_series(percent_series, limit=len(x_values)),
                    "source_name": source_name,
                    "evidence_id": evidence_id,
                }
            )
        for currency_item in currency_series:
            charts.append(
                {
                    "chart_id": (
                        f"dataset-currency-bars-{evidence_id}-"
                        f"{_slug(str(currency_item['key']))}"
                    ),
                    "title": f"{currency_item['label']} Trend",
                    "subtitle": (
                        f"Period-by-period values parsed from cited CSV evidence "
                        f"using {x_axis} as the x-axis."
                    ),
                    "chart_type": "time_bar",
                    "x_axis": x_axis,
                    "x_values": x_values,
                    "series": _trim_series([currency_item], limit=len(x_values)),
                    "source_name": source_name,
                    "evidence_id": evidence_id,
                }
            )
        if not percent_series and not currency_series and numeric_series:
            charts.append(
                {
                    "chart_id": f"dataset-numeric-trend-{evidence_id}",
                    "title": f"Numeric Trend: {source_name}",
                    "subtitle": (
                        f"Numeric columns parsed from cited CSV evidence using "
                        f"{x_axis} as the x-axis."
                    ),
                    "chart_type": "line",
                    "x_axis": x_axis,
                    "x_values": x_values,
                    "series": _trim_series(numeric_series, limit=len(x_values)),
                    "source_name": source_name,
                    "evidence_id": evidence_id,
                }
            )
    return charts


def _parse_csv_rows(text: str) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(StringIO(text.strip()))
        rows = [
            {str(key): str(value or "").strip() for key, value in row.items() if key}
            for row in reader
        ]
    except csv.Error:
        return []
    return [row for row in rows if any(value for value in row.values())]


def _dataset_x_axis(rows: list[dict[str, str]]) -> str:
    columns = list(rows[0].keys())
    preferred = {"date", "year", "period", "quarter", "month"}
    for column in columns:
        if column.strip().lower() in preferred:
            return column
    for column in columns:
        if any(_parse_number(row.get(column, "")) is None for row in rows):
            return column
    return columns[0]


def _dataset_numeric_series(
    rows: list[dict[str, str]],
    *,
    x_axis: str,
) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for column in rows[0].keys():
        if column == x_axis:
            continue
        values = [_parse_number(row.get(column, "")) for row in rows[:8]]
        numeric_values = [value for value in values if value is not None]
        if len(numeric_values) < 2:
            continue
        unit = _column_unit(column)
        series.append(
            {
                "key": column,
                "label": _column_label(column),
                "unit": unit,
                "values": [
                    {
                        "x": str(rows[index].get(x_axis, "")).strip(),
                        "value": value,
                        "display_value": _format_series_value(value, unit),
                    }
                    for index, value in enumerate(values)
                    if value is not None
                ],
            }
        )
    return series


def _filter_series_for_focus(
    series: list[dict[str, Any]],
    *,
    focus_terms: set[str],
) -> list[dict[str, Any]]:
    meaningful_terms = focus_terms - _GENERIC_FOCUS_TERMS
    if not meaningful_terms:
        return series

    scored_series = [
        (
            len(meaningful_terms & _series_terms(item)),
            index,
            item,
        )
        for index, item in enumerate(series)
    ]
    max_score = max((score for score, _, _ in scored_series), default=0)
    if max_score == 0:
        return []

    minimum_score = 2 if max_score >= 2 else 1
    return [
        item
        for score, _, item in sorted(scored_series, key=lambda scored: scored[1])
        if score >= minimum_score
    ]


_FOCUS_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "based",
    "by",
    "can",
    "did",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "local",
    "me",
    "of",
    "on",
    "or",
    "source",
    "strongest",
    "tell",
    "the",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "why",
    "with",
}

_GENERIC_FOCUS_TERMS = {
    "analysis",
    "article",
    "asset",
    "brief",
    "chart",
    "data",
    "dataset",
    "document",
    "evidence",
    "file",
    "indicator",
    "invest",
    "investment",
    "market",
    "metric",
    "report",
    "summarize",
    "summary",
    "trend",
    "value",
}

_FOCUS_TERM_NORMALIZATION = {
    "assets": "asset",
    "banks": "bank",
    "charts": "chart",
    "datasets": "dataset",
    "documents": "document",
    "files": "file",
    "flows": "flow",
    "indicators": "indicator",
    "investments": "investment",
    "markets": "market",
    "metrics": "metric",
    "reports": "report",
    "returns": "return",
    "sources": "source",
    "summaries": "summary",
    "trends": "trend",
    "values": "value",
    "yields": "yield",
}


def _focus_terms(text: str) -> set[str]:
    return {
        term
        for term in _normalized_focus_terms(text)
        if term not in _FOCUS_STOPWORDS and not term.isdigit()
    }


def _series_terms(series: dict[str, Any]) -> set[str]:
    return set(
        _normalized_focus_terms(f"{series.get('key', '')} {series.get('label', '')}")
    )


def _normalized_focus_terms(text: str) -> list[str]:
    return [
        _FOCUS_TERM_NORMALIZATION.get(term, term)
        for term in re.findall(r"[a-z0-9]+", text.lower())
        if term
    ]


def _trim_series(
    series: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    trimmed: list[dict[str, Any]] = []
    for item in series:
        copied = dict(item)
        values = copied.get("values", [])
        copied["values"] = values[:limit] if isinstance(values, list) else []
        trimmed.append(copied)
    return trimmed


def _parse_number(value: str) -> float | None:
    normalized = value.strip().replace(",", "")
    if not normalized:
        return None
    negative = normalized.startswith("(") and normalized.endswith(")")
    normalized = normalized.strip("()").removeprefix("$").removesuffix("%")
    try:
        number = float(normalized)
    except ValueError:
        return None
    return -number if negative else number


def _column_unit(column: str) -> str:
    normalized = column.lower()
    if (
        normalized.endswith("_pct")
        or normalized.endswith("_percent")
        or "%" in normalized
        or normalized in {"return", "yield", "margin", "share"}
        or any(word in normalized for word in ("return_", "yield_", "margin", "share"))
    ):
        return "%"
    if normalized.endswith("_b") or normalized.endswith("_bn"):
        return "$B"
    if normalized.endswith("_m") or normalized.endswith("_mm"):
        return "$M"
    if normalized.endswith("_k"):
        return "$K"
    if normalized.startswith("usd_") or normalized.endswith("_usd"):
        return "$"
    return ""


def _column_label(column: str) -> str:
    label = re.sub(r"(_pct|_percent|_bn|_mm|_usd|_b|_m|_k)$", "", column, flags=re.I)
    words = label.replace("_", " ").replace("-", " ").split()
    titled = [
        word.upper() if word.lower() in {"etf", "eps", "fcf"} else word.title()
        for word in words
    ]
    return " ".join(titled) or column


def _format_series_value(value: float, unit: str) -> str:
    if unit == "%":
        return f"{_format_chart_number(value)}%"
    if unit == "$B":
        return _format_signed_money(value, "B")
    if unit == "$M":
        return _format_signed_money(value, "M")
    if unit == "$K":
        return _format_signed_money(value, "K")
    if unit == "$":
        return _format_signed_money(value, "")
    return _format_chart_number(value)


def _format_signed_money(value: float, suffix: str) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${_format_chart_number(abs(value))}{suffix}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "series"


def _extract_percent_points(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    seen: set[tuple[str, float, int]] = set()
    for item in evidence:
        for sentence in _sentences(str(item.get("excerpt", ""))):
            for match in _PERCENT_PATTERN.finditer(sentence):
                value = float(match.group("value"))
                label = _metric_label(
                    sentence[: match.start()],
                    fallback=f"{item.get('source_name', 'source')} metric",
                )
                evidence_id = int(item.get("evidence_id", 0) or 0)
                key = (label.lower(), value, evidence_id)
                if key in seen:
                    continue
                seen.add(key)
                points.append(
                    {
                        "label": label,
                        "value": value,
                        "display_value": f"{_format_chart_number(value)}%",
                        "source_name": str(item.get("source_name", "")),
                        "evidence_id": evidence_id,
                    }
                )
    return points


def _extract_money_points(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    seen: set[tuple[str, float, int]] = set()
    for item in evidence:
        for sentence in _sentences(str(item.get("excerpt", ""))):
            for match in _MONEY_PATTERN.finditer(sentence):
                value = _money_to_millions(match.group("value"), match.group("scale"))
                label = _metric_label(
                    sentence[: match.start()],
                    fallback=f"{item.get('source_name', 'source')} dollar metric",
                )
                evidence_id = int(item.get("evidence_id", 0) or 0)
                key = (label.lower(), value, evidence_id)
                if key in seen:
                    continue
                seen.add(key)
                points.append(
                    {
                        "label": label,
                        "value": value,
                        "display_value": _format_money_millions(value),
                        "source_name": str(item.get("source_name", "")),
                        "evidence_id": evidence_id,
                    }
                )
    return points


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_PATTERN.split(text)
        if sentence.strip()
    ]


def _metric_label(prefix: str, *, fallback: str) -> str:
    label = prefix.strip(" \t\n\r,;:-")
    for separator in (" while ", " and ", " but ", ";", ","):
        if separator in label:
            label = label.rsplit(separator, 1)[-1]
    words = [
        word.strip(" \t\n\r,;:-()[]{}")
        for word in label.split()
        if word.strip(" \t\n\r,;:-()[]{}")
    ]
    while words and words[-1].lower() in _TRAILING_LABEL_WORDS:
        words.pop()
    while words and words[0].lower() in {"a", "an", "the"}:
        words.pop(0)
    if not words:
        return fallback
    return " ".join(words[-7:])


def _money_to_millions(value_text: str, scale: str | None) -> float:
    value = float(value_text.replace(",", ""))
    normalized_scale = (scale or "").lower()
    if normalized_scale == "b":
        return value * 1000
    if normalized_scale == "m":
        return value
    if normalized_scale == "k":
        return value / 1000
    return value / 1_000_000


def _format_chart_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _format_money_millions(value: float) -> str:
    absolute_value = abs(value)
    sign = "-" if value < 0 else ""
    if absolute_value >= 1000:
        return f"{sign}${_format_chart_number(absolute_value / 1000)}B"
    if absolute_value >= 1:
        return f"{sign}${_format_chart_number(absolute_value)}M"
    return f"{sign}${_format_chart_number(absolute_value * 1000)}K"


def _normalize_evidence_excerpt(excerpt: str, *, source_type: str) -> str:
    if source_type == "csv":
        return excerpt.strip()

    text = " ".join(excerpt.split())
    if not text.startswith("#"):
        return text.strip()

    parts = text.removeprefix("#").strip().split()
    for index, token in enumerate(parts[1:], start=1):
        if token[:1].islower():
            return " ".join(parts[max(0, index - 1) :]).strip()
    return " ".join(parts).strip()


def _sections(
    *,
    question: str,
    answer: str,
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    critic: dict[str, Any],
) -> list[dict[str, Any]]:
    claim_body = (
        "\n".join(
            f"- {_plain_model_text(str(claim['claim_text']))}" for claim in claims
        )
        if claims
        else "No supported claim was generated from the local evidence."
    )
    evidence_body = (
        "\n".join(f"- {item['source_name']}: {item['excerpt']}" for item in evidence)
        if evidence
        else "No supporting source was retrieved."
    )
    finding_lines = [
        f"- {finding['severity']}: {finding['message']}"
        for finding in critic.get("findings", [])
    ]
    critic_body = (
        f"Status: {critic['status']}.\n" + "\n".join(finding_lines)
        if finding_lines
        else f"Status: {critic['status']}."
    )
    evidence_ids = [
        item["evidence_id"]
        for item in evidence
        if isinstance(item.get("evidence_id"), int)
    ]
    clean_answer = _plain_model_text(answer)
    thesis_body = (
        "The selected evidence supports the following thesis:\n" + claim_body
        if claims
        else "The available local evidence does not support an investment thesis."
    )
    counter_evidence_body, counter_evidence_ids = _counter_evidence_section(
        claims=claims,
        evidence=evidence,
    )
    risks_body = _risks_section(evidence=evidence, charts=charts)
    falsification_body = _falsification_section(claims=claims)
    implications_body = _investment_implications_section(
        question=question,
        claims=claims,
    )
    sections = [
        {
            "heading": "Executive Summary",
            "body": clean_answer or "No answer was generated.",
            "evidence_ids": evidence_ids,
        },
        {
            "heading": "Investment Thesis",
            "body": thesis_body,
            "evidence_ids": evidence_ids,
        },
        {
            "heading": "Key Claims",
            "body": claim_body,
            "evidence_ids": evidence_ids,
        },
    ]
    chart_body = _chart_interpretation_body(charts)
    if chart_body:
        sections.append(
            {
                "heading": "Data Interpretation",
                "body": chart_body,
                "evidence_ids": evidence_ids,
            }
        )
    sections.extend(
        [
            {
                "heading": "Supporting Evidence",
                "body": evidence_body,
                "evidence_ids": evidence_ids,
            },
            {
                "heading": "Counter-Evidence and Gaps",
                "body": counter_evidence_body,
                "evidence_ids": counter_evidence_ids,
            },
            {
                "heading": "Risks and Uncertainties",
                "body": risks_body,
                "evidence_ids": evidence_ids,
            },
            {
                "heading": "Falsification Conditions",
                "body": falsification_body,
                "evidence_ids": evidence_ids,
            },
            {
                "heading": "Investment Implications",
                "body": implications_body,
                "evidence_ids": evidence_ids,
            },
            {
                "heading": "Critic Review",
                "body": critic_body,
                "evidence_ids": evidence_ids,
            },
        ]
    )
    return sections


def _counter_evidence_section(
    *,
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> tuple[str, list[int]]:
    evidence_by_id = {
        item["evidence_id"]: item
        for item in evidence
        if isinstance(item.get("evidence_id"), int)
    }
    opposing_ids: list[int] = []
    for claim in claims:
        relations = claim.get("relations", {})
        if not isinstance(relations, dict):
            continue
        for raw_id, relation in relations.items():
            if str(relation).lower() != "opposes":
                continue
            try:
                evidence_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if evidence_id in evidence_by_id and evidence_id not in opposing_ids:
                opposing_ids.append(evidence_id)

    if not opposing_ids:
        return (
            "No opposing evidence was retrieved from the selected local sources. "
            "This is an evidence-coverage gap, not proof that no counterargument "
            "exists; review independent and newer sources before acting.",
            [],
        )
    lines = [
        f"- {evidence_by_id[evidence_id]['source_name']}: "
        f"{evidence_by_id[evidence_id]['excerpt']}"
        for evidence_id in opposing_ids
    ]
    return "\n".join(lines), opposing_ids


def _risks_section(
    *,
    evidence: list[dict[str, Any]],
    charts: list[dict[str, Any]],
) -> str:
    source_count = len({item.get("source_name") for item in evidence})
    lines = [
        f"- Evidence coverage risk: this brief uses {source_count} selected local "
        "source(s) and may omit material external information.",
        "- Timing risk: the report does not use live market prices or events after "
        "the cited sources' data dates.",
    ]
    if charts:
        lines.append(
            "- Interpretation risk: historical chart relationships do not by "
            "themselves establish causation or predict future returns."
        )
    return "\n".join(lines)


def _falsification_section(*, claims: list[dict[str, Any]]) -> str:
    if not claims:
        return (
            "The thesis should be rejected unless a source-backed claim can be "
            "established."
        )
    lines = [
        "- Reconsider the thesis if newer, higher-grade evidence directly "
        f"contradicts: {_plain_model_text(str(claim['claim_text']))}"
        for claim in claims[:3]
    ]
    lines.append(
        "- Re-run the research if a cited source changes, its as-of date becomes "
        "stale for the decision, or its content hash no longer matches."
    )
    return "\n".join(lines)


def _investment_implications_section(
    *,
    question: str,
    claims: list[dict[str, Any]],
) -> str:
    lines = [
        "- Use this brief as research input, not as a personalized instruction to "
        "buy, sell, or size a position.",
        f"- Decision focus: {question.strip()}",
    ]
    lines.extend(
        f"- Monitor whether the cited evidence continues to support: "
        f"{_plain_model_text(str(claim['claim_text']))}"
        for claim in claims[:2]
    )
    return "\n".join(lines)


def _chart_interpretation_body(charts: list[dict[str, Any]]) -> str:
    lines = [
        f"- {chart.get('title', 'Chart')}: {chart.get('narrative')}"
        for chart in charts
        if chart.get("narrative")
    ]
    if not lines:
        return ""
    lines.append(
        "- These visuals are parsed from cited local evidence and should be "
        "read as source-backed historical indicators, not live market data or "
        "investment advice."
    )
    return "\n".join(lines)


def _render_section(section: dict[str, Any]) -> str:
    heading = escape(str(section.get("heading", "")))
    body = _render_body(str(section.get("body", "")))
    evidence_ids = section.get("evidence_ids", [])
    citation = ""
    if isinstance(evidence_ids, list) and evidence_ids:
        citation = (
            '<p class="citation">Evidence IDs: '
            + escape(", ".join(str(value) for value in evidence_ids))
            + "</p>"
        )
    return f"""<section class="section">
  <h2>{heading}</h2>
  {body}
  {citation}
</section>"""


def _render_charts(charts: Any) -> str:
    if not isinstance(charts, list) or not charts:
        return ""
    rendered = [
        _render_chart(chart)
        for chart in charts
        if isinstance(chart, dict) and _chart_has_data(chart)
    ]
    if not rendered:
        return ""
    return f"""<section class="section">
  <h2>Data Analysis</h2>
  <div class="chart-grid">{"".join(rendered)}</div>
</section>"""


def _render_chart(chart: dict[str, Any]) -> str:
    chart_type = str(chart.get("chart_type", "bar"))
    if chart_type == "line":
        return _render_line_chart(chart)
    if chart_type == "time_bar":
        return _render_time_bar_chart(chart)
    return _render_metric_bar_chart(chart)


def _render_chart_narrative(chart: dict[str, Any]) -> str:
    narrative = str(chart.get("narrative", "")).strip()
    if not narrative:
        return ""
    return (
        '<p class="chart-insight"><strong>What it shows:</strong> '
        + escape(narrative)
        + "</p>"
    )


def _chart_narrative(chart: dict[str, Any]) -> str:
    chart_type = str(chart.get("chart_type", ""))
    if chart_type == "line":
        return _series_chart_narrative(chart, max_sentences=4)
    if chart_type == "time_bar":
        return _series_chart_narrative(chart, max_sentences=1)
    return _metric_chart_narrative(chart)


def _series_chart_narrative(
    chart: dict[str, Any],
    *,
    max_sentences: int,
) -> str:
    series = chart.get("series", [])
    if not isinstance(series, list):
        return ""
    sentences: list[str] = []
    for item in series[:max_sentences]:
        if not isinstance(item, dict):
            continue
        sentence = _series_narrative_sentence(item)
        if sentence:
            sentences.append(sentence)
    return " ".join(sentences)


def _series_narrative_sentence(item: dict[str, Any]) -> str:
    values = item.get("values", [])
    if not isinstance(values, list):
        return ""
    points = [
        (
            str(value_item.get("x", "")).strip(),
            float(value_item.get("value", 0.0)),
            str(value_item.get("display_value", "")),
        )
        for value_item in values
        if isinstance(value_item, dict)
    ]
    if len(points) < 2:
        return ""
    label = str(item.get("label", "Series"))
    unit = str(item.get("unit", ""))
    first = points[0]
    last = points[-1]
    peak = max(points, key=lambda point: point[1])
    trough = min(points, key=lambda point: point[1])
    direction = _trend_direction(first[1], last[1])
    sentence = (
        f"{label} {direction} from {_display_point_value(first, unit)} in "
        f"{first[0]} to {_display_point_value(last, unit)} in {last[0]}"
    )
    details: list[str] = []
    if peak[0] not in {first[0], last[0]}:
        details.append(f"peaked at {_display_point_value(peak, unit)} in {peak[0]}")
    if trough[0] not in {first[0], last[0]}:
        details.append(
            f"bottomed at {_display_point_value(trough, unit)} in {trough[0]}"
        )
    crossing = _first_positive_period(points)
    if crossing is not None and first[1] < 0 <= last[1]:
        details.append(f"turned positive in {crossing}")
    if details:
        sentence += ", and " + "; ".join(details)
    return sentence + "."


def _metric_chart_narrative(chart: dict[str, Any]) -> str:
    data = chart.get("data", [])
    if not isinstance(data, list):
        return ""
    points = [
        (
            str(point.get("label", "Metric")),
            float(point.get("value", 0.0)),
            str(point.get("display_value", "")),
        )
        for point in data
        if isinstance(point, dict)
    ]
    if not points:
        return ""
    largest = max(points, key=lambda point: abs(point[1]))
    return (
        f"The largest cited value is {largest[2] or _format_chart_number(largest[1])} "
        f"for {largest[0]}, so the chart should be read as a comparison of cited "
        "indicators rather than a full market dataset."
    )


def _trend_direction(first_value: float, last_value: float) -> str:
    if last_value > first_value:
        return "rose"
    if last_value < first_value:
        return "fell"
    return "was unchanged"


def _display_point_value(point: tuple[str, float, str], unit: str) -> str:
    display_value = point[2].strip()
    if display_value:
        return display_value
    return _format_series_value(point[1], unit)


def _first_positive_period(points: list[tuple[str, float, str]]) -> str | None:
    for period, value, _display in points:
        if value > 0:
            return period
    return None


def _chart_has_data(chart: dict[str, Any]) -> bool:
    data = chart.get("data")
    series = chart.get("series")
    return bool(data) or bool(series)


def _render_metric_bar_chart(chart: dict[str, Any]) -> str:
    data = chart.get("data", [])
    if not isinstance(data, list):
        return ""
    values = [
        abs(float(point.get("value", 0.0))) for point in data if isinstance(point, dict)
    ]
    max_value = max(values) if values else 1.0
    title = escape(str(chart.get("title", "Chart")))
    subtitle = escape(str(chart.get("subtitle", "")))
    narrative = _render_chart_narrative(chart)
    rows = []
    for point in data:
        if not isinstance(point, dict):
            continue
        value = float(point.get("value", 0.0))
        width = 0.0 if max_value == 0 else min(100.0, abs(value) / max_value * 100)
        label = escape(str(point.get("label", "Metric")))
        display_value = escape(str(point.get("display_value", value)))
        source_name = escape(str(point.get("source_name", "")))
        evidence_id = escape(str(point.get("evidence_id", "")))
        fill_class = "chart-fill negative" if value < 0 else "chart-fill"
        rows.append(
            f"""<div class="chart-row">
  <span class="chart-label">{label}</span>
  <span class="chart-track" aria-hidden="true"><span class="{fill_class}" style="width: {width:.1f}%"></span></span>
  <span class="chart-value">{display_value}</span>
  <span class="chart-source">Source: {source_name} · Evidence ID: {evidence_id}</span>
</div>"""
        )
    return f"""<article class="chart-card">
  <h3>{title}</h3>
  <p class="subtitle">{subtitle}</p>
  {narrative}
  {"".join(rows)}
</article>"""


def _render_line_chart(chart: dict[str, Any]) -> str:
    series = chart.get("series", [])
    if not isinstance(series, list) or not series:
        return ""
    title = escape(str(chart.get("title", "Trend Chart")))
    subtitle = escape(str(chart.get("subtitle", "")))
    narrative = _render_chart_narrative(chart)
    source_name = escape(str(chart.get("source_name", "")))
    evidence_id = escape(str(chart.get("evidence_id", "")))
    values = _series_values(series)
    if not values:
        return ""
    y_min, y_max = _chart_domain(values)
    width = 720
    height = 270
    left = 54
    right = 24
    top = 24
    bottom = 56
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_values = _chart_x_values(chart, series)
    x_count = max(1, len(x_values))
    zero_y = _scale_y(0, y_min, y_max, top, plot_height)
    y_min_label = _axis_label(y_min, series)
    y_max_label = _axis_label(y_max, series)
    polylines = []
    point_nodes = []
    legend_items = []
    for index, item in enumerate(series):
        if not isinstance(item, dict):
            continue
        color = _chart_color(index)
        label = escape(str(item.get("label", "Series")))
        unit = str(item.get("unit", ""))
        points: list[str] = []
        for value_item in item.get("values", []):
            if not isinstance(value_item, dict):
                continue
            x_label = str(value_item.get("x", ""))
            value = float(value_item.get("value", 0.0))
            x_position = _scale_x(x_label, x_values, left, plot_width, x_count)
            y_position = _scale_y(value, y_min, y_max, top, plot_height)
            display_value = escape(
                str(value_item.get("display_value", _format_series_value(value, unit)))
            )
            points.append(f"{x_position:.1f},{y_position:.1f}")
            point_nodes.append(
                f"""<circle cx="{x_position:.1f}" cy="{y_position:.1f}" r="4" fill="{color}">
  <title>{label}: {display_value} ({escape(x_label)})</title>
</circle>"""
            )
        if len(points) >= 2:
            polylines.append(
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{color}" stroke-width="3" stroke-linecap="round" '
                'stroke-linejoin="round" />'
            )
        legend_items.append(
            f'<li><span class="legend-swatch" style="background: {color}"></span>{label}</li>'
        )
    x_labels = _render_x_axis_labels(x_values, left, plot_width, x_count, height)
    return f"""<article class="chart-card">
  <h3>{title}</h3>
  <p class="subtitle">{subtitle}</p>
  {narrative}
  <svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
    <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" />
    <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" />
    <line class="chart-gridline" x1="{left}" y1="{zero_y:.1f}" x2="{width - right}" y2="{zero_y:.1f}" />
    <text class="chart-axis-label" x="8" y="{top + 4}">{escape(y_max_label)}</text>
    <text class="chart-axis-label" x="8" y="{top + plot_height}">{escape(y_min_label)}</text>
    {"".join(polylines)}
    {"".join(point_nodes)}
    {x_labels}
  </svg>
  <ul class="svg-legend">{"".join(legend_items)}</ul>
  <p class="chart-source-line">Source: {source_name} · Evidence ID: {evidence_id}</p>
</article>"""


def _render_time_bar_chart(chart: dict[str, Any]) -> str:
    series = chart.get("series", [])
    if not isinstance(series, list) or not series or not isinstance(series[0], dict):
        return ""
    item = series[0]
    values = item.get("values", [])
    if not isinstance(values, list) or not values:
        return ""
    title = escape(str(chart.get("title", "Bar Chart")))
    subtitle = escape(str(chart.get("subtitle", "")))
    narrative = _render_chart_narrative(chart)
    source_name = escape(str(chart.get("source_name", "")))
    evidence_id = escape(str(chart.get("evidence_id", "")))
    unit = str(item.get("unit", ""))
    raw_values = [
        float(value_item.get("value", 0.0))
        for value_item in values
        if isinstance(value_item, dict)
    ]
    if not raw_values:
        return ""
    y_min, y_max = _chart_domain(raw_values)
    width = 720
    height = 270
    left = 54
    right = 24
    top = 24
    bottom = 56
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_values = _chart_x_values(chart, series)
    x_count = max(1, len(x_values))
    slot_width = plot_width / x_count
    bar_width = min(54, slot_width * 0.58)
    baseline = _scale_y(0, y_min, y_max, top, plot_height)
    bars = []
    for value_item in values:
        if not isinstance(value_item, dict):
            continue
        x_label = str(value_item.get("x", ""))
        value = float(value_item.get("value", 0.0))
        center_x = _scale_x(x_label, x_values, left, plot_width, x_count)
        y_position = _scale_y(value, y_min, y_max, top, plot_height)
        rect_y = min(y_position, baseline)
        rect_height = max(2, abs(baseline - y_position))
        color = _chart_color(0) if value >= 0 else "#c2415d"
        display_value = escape(
            str(value_item.get("display_value", _format_series_value(value, unit)))
        )
        bars.append(
            f"""<rect x="{center_x - bar_width / 2:.1f}" y="{rect_y:.1f}" width="{bar_width:.1f}" height="{rect_height:.1f}" rx="4" fill="{color}">
  <title>{display_value} ({escape(x_label)})</title>
</rect>"""
        )
    x_labels = _render_x_axis_labels(x_values, left, plot_width, x_count, height)
    return f"""<article class="chart-card">
  <h3>{title}</h3>
  <p class="subtitle">{subtitle}</p>
  {narrative}
  <svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
    <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" />
    <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" />
    <line class="chart-gridline" x1="{left}" y1="{baseline:.1f}" x2="{width - right}" y2="{baseline:.1f}" />
    <text class="chart-axis-label" x="8" y="{top + 4}">{escape(_axis_label(y_max, series))}</text>
    <text class="chart-axis-label" x="8" y="{top + plot_height}">{escape(_axis_label(y_min, series))}</text>
    {"".join(bars)}
    {x_labels}
  </svg>
  <p class="chart-source-line">Source: {source_name} · Evidence ID: {evidence_id}</p>
</article>"""


def _series_values(series: list[Any]) -> list[float]:
    values: list[float] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        for value_item in item.get("values", []):
            if isinstance(value_item, dict):
                values.append(float(value_item.get("value", 0.0)))
    return values


def _chart_domain(values: list[float]) -> tuple[float, float]:
    y_min = min(values + [0.0])
    y_max = max(values + [0.0])
    if y_min == y_max:
        padding = 1.0 if y_min == 0 else abs(y_min) * 0.1
        return y_min - padding, y_max + padding
    padding = (y_max - y_min) * 0.12
    return y_min - padding, y_max + padding


def _chart_x_values(chart: dict[str, Any], series: list[Any]) -> list[str]:
    raw_values = chart.get("x_values", [])
    if isinstance(raw_values, list) and raw_values:
        return [str(value) for value in raw_values]
    labels: list[str] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        for value_item in item.get("values", []):
            if not isinstance(value_item, dict):
                continue
            label = str(value_item.get("x", ""))
            if label not in labels:
                labels.append(label)
    return labels


def _scale_x(
    label: str,
    x_values: list[str],
    left: int,
    plot_width: int,
    x_count: int,
) -> float:
    try:
        index = x_values.index(label)
    except ValueError:
        index = 0
    if x_count <= 1:
        return left + plot_width / 2
    return left + (plot_width * index / (x_count - 1))


def _scale_y(
    value: float,
    y_min: float,
    y_max: float,
    top: int,
    plot_height: int,
) -> float:
    if y_max == y_min:
        return top + plot_height / 2
    ratio = (value - y_min) / (y_max - y_min)
    return top + plot_height - ratio * plot_height


def _render_x_axis_labels(
    x_values: list[str],
    left: int,
    plot_width: int,
    x_count: int,
    height: int,
) -> str:
    labels = []
    for label in x_values:
        x_position = _scale_x(label, x_values, left, plot_width, x_count)
        labels.append(
            f'<text class="chart-axis-label" x="{x_position:.1f}" '
            f'y="{height - 24}" text-anchor="middle">{escape(label)}</text>'
        )
    return "".join(labels)


def _axis_label(value: float, series: list[Any]) -> str:
    unit = ""
    for item in series:
        if isinstance(item, dict) and isinstance(item.get("unit"), str):
            unit = str(item["unit"])
            break
    return _format_series_value(value, unit)


_CHART_COLORS = ("#2f7d62", "#4c7bd9", "#d68132", "#8b5cf6", "#c2415d")


def _chart_color(index: int) -> str:
    return _CHART_COLORS[index % len(_CHART_COLORS)]


def _render_body(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    rendered: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        if not list_items:
            return
        rendered.append(
            "<ul>"
            + "".join(f"<li>{escape(item)}</li>" for item in list_items)
            + "</ul>"
        )
        list_items.clear()

    for line in lines:
        bullet = re.match(r"^(?:-|\*)\s+(.*)$", line)
        if bullet is not None:
            list_items.append(_plain_model_text(bullet.group(1)))
            continue
        flush_list()
        rendered.append(f"<p>{escape(_plain_model_text(line))}</p>")
    flush_list()
    return "".join(rendered) or "<p></p>"


def _plain_model_text(value: str) -> str:
    cleaned = value.replace("**", "").replace("`", "")
    cleaned = re.sub(r"(?m)^\s*\*\s+", "- ", cleaned)
    cleaned = re.sub(r"\s+\*\s+", "; ", cleaned)
    cleaned = cleaned.replace(":;", ":")
    return cleaned.strip()


def _render_evidence(evidence: Any) -> str:
    if not isinstance(evidence, list) or not evidence:
        return ""
    items = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        source_name = escape(str(item.get("source_name", "")))
        excerpt = escape(str(item.get("excerpt", "")))
        evidence_id = escape(str(item.get("evidence_id", "")))
        items.append(
            f"<li><strong>Source: {source_name}</strong>"
            f"<p>{excerpt}</p>"
            f'<p class="citation">Evidence ID: {evidence_id}</p></li>'
        )
    return f"""<section class="section">
  <h2>Evidence Ledger</h2>
  <ul class="evidence-list">{"".join(items)}</ul>
</section>"""
