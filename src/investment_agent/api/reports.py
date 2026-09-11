from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.api.style_packs import resolve_style_pack
from investment_agent.harness.agent_loop import AgentEvidenceSource, AgentLoopResult
from investment_agent.repositories import (
    AgentRunRepository,
    ClaimCreate,
    ReportCreate,
    ReportRepository,
)
from investment_agent.research.claims import ClaimGenerator
from investment_agent.research.critic import EvidenceCritic, include_claim_verification
from investment_agent.research.quality import (
    is_no_evidence_answer,
    is_substantive_report_answer,
)
from investment_agent.research.reports import (
    build_research_report,
    build_web_research_report,
)
from investment_agent.sources import source_display_name
from investment_agent.storage import Chunk, Claim, EvidenceItem
from investment_agent.style_packs import (
    GENERAL_RESEARCH_STYLE_PACK,
    StylePackDefinition,
)

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportGenerateRequest(BaseModel):
    topic: str = Field(min_length=1)
    question: str | None = None
    source_run_id: int | None = Field(default=None, gt=0)
    as_of_date: date | None = None
    document_id: int | None = Field(default=None, gt=0)
    sensitivity: str = Field(default="internal", min_length=1)


class ReportResponse(BaseModel):
    report_id: int
    title: str
    report_type: str
    status: str
    run_id: int
    html_url: str
    report_json: dict[str, Any]


@router.post(
    "/generate",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_report(
    request: ReportGenerateRequest,
    session: Session = Depends(get_db_session),
) -> ReportResponse:
    if request.source_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Cannot generate a report without a source-backed Ask run. "
                "Ask a question first, then generate a report from that trace."
            ),
        )

    question = request.question or _default_question(request.topic)
    run_repository = AgentRunRepository(session)
    source_run = run_repository.get_run(request.source_run_id)
    if source_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source run not found: {request.source_run_id}",
        )
    if source_run.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot generate a report from an incomplete Ask run.",
        )
    metadata = source_run.metadata_json or {}
    raw_style_pack = metadata.get("style_pack")
    style_pack_id = _metadata_string(metadata, "style_pack_id")
    if style_pack_id == GENERAL_RESEARCH_STYLE_PACK.id:
        style_pack = GENERAL_RESEARCH_STYLE_PACK
    elif isinstance(raw_style_pack, dict):
        style_pack = StylePackDefinition.model_validate(raw_style_pack)
    else:
        style_pack = resolve_style_pack(session, style_pack_id)
    web_sources = metadata.get("web_sources")
    stored_answer = _stored_answer(session, run_id=source_run.id, metadata=metadata)
    if isinstance(web_sources, list) and web_sources and stored_answer:
        search_metadata = metadata.get("search")
        gate_metadata = (
            search_metadata.get("evidence_gate")
            if isinstance(search_metadata, dict)
            else None
        )
        if (
            not isinstance(gate_metadata, dict)
            or gate_metadata.get("decision") != "supported"
            or gate_metadata.get("report_eligible") is not True
            or metadata.get("citation_status") != "validated"
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Cannot generate a web report until the Evidence Gate accepts "
                    "enough support and the answer preserves valid Argus citation IDs."
                ),
            )
        if not is_substantive_report_answer(stored_answer):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "The answer is useful as a short extract but is incomplete or too "
                    "thin for a research report. Refine Ask or collect broader cited "
                    "evidence before generating HTML."
                ),
            )
        generated_report = build_web_research_report(
            topic=request.topic,
            question=question,
            run_id=source_run.id,
            run_key=source_run.run_key,
            answer=stored_answer,
            web_sources=[item for item in web_sources if isinstance(item, dict)],
            grounding_method=(
                _metadata_string(metadata, "grounding_method")
                or "independent web evidence retrieval"
            ),
            evidence_scope=(_metadata_string(metadata, "evidence_scope") or "web"),
            total_tokens=source_run.total_tokens,
            total_estimated_cost_usd=float(source_run.total_estimated_cost_usd),
            iterations=_metadata_int(metadata, "iterations"),
            style_pack=style_pack,
        )
        report = ReportRepository(session).create_report(
            ReportCreate(
                title=generated_report.title,
                report_type=generated_report.report_type,
                status=generated_report.status,
                report_json=generated_report.report_json,
                rendered_html=generated_report.rendered_html,
            )
        )
        return _report_response(
            report_id=report.id,
            title=report.title,
            report_type=report.report_type,
            status=report.status,
            report_json=report.report_json,
        )

    search_metadata = metadata.get("search")
    gate_metadata = (
        search_metadata.get("evidence_gate")
        if isinstance(search_metadata, dict)
        else None
    )
    if isinstance(gate_metadata, dict) and (
        gate_metadata.get("decision") != "supported"
        or gate_metadata.get("report_eligible") is not True
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Cannot generate a report without local evidence or from weak or "
                "unverified evidence: the Evidence Gate did not accept enough "
                "direct, complete support. Refine the question or collect stronger "
                "evidence first."
            ),
        )

    agent_result = _agent_result_from_run(session, run_id=request.source_run_id)
    critic = EvidenceCritic().review_answer(
        answer=agent_result.answer,
        sources=agent_result.sources,
    )
    claims = ClaimGenerator().generate(
        answer=agent_result.answer,
        sources=agent_result.sources,
    )
    critic = include_claim_verification(critic, claims)
    if not _can_generate_report(agent_result.answer, claims):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Cannot generate a report without local evidence. Ask a question "
                "that returns at least one source-backed answer first."
            ),
        )
    if critic.status != "passed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Cannot generate a report from weak or unverified evidence. "
                "Refine the question or select a better source until Evidence "
                "validation passes."
            ),
        )
    has_structured_dataset = any(
        source.source_type == "csv" and source.excerpt.strip()
        for source in agent_result.sources
    )
    if (
        not is_substantive_report_answer(agent_result.answer)
        and not has_structured_dataset
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The answer is useful as a short extract but does not contain enough "
                "complete evidence-backed analysis for a research report. Refine Ask "
                "or collect broader evidence before generating HTML."
            ),
        )
    generated_report = build_research_report(
        topic=request.topic,
        question=question,
        agent_result=agent_result,
        claims=claims,
        critic=critic,
        style_pack=style_pack,
    )
    report = ReportRepository(session).create_report(
        ReportCreate(
            title=generated_report.title,
            report_type=generated_report.report_type,
            status=generated_report.status,
            report_json=generated_report.report_json,
            rendered_html=generated_report.rendered_html,
        )
    )
    for claim in claims:
        run_repository.record_claim(
            ClaimCreate(
                report_id=report.id,
                run_id=agent_result.run_id,
                claim_text=claim.claim_text,
                evidence_ids=list(claim.evidence_ids),
                relations=claim.relations,
                confidence=claim.confidence,
            )
        )

    return _report_response(
        report_id=report.id,
        title=report.title,
        report_type=report.report_type,
        status=report.status,
        report_json=report.report_json,
    )


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: int,
    session: Session = Depends(get_db_session),
) -> ReportResponse:
    report = ReportRepository(session).get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found: {report_id}",
        )
    return _report_response(
        report_id=report.id,
        title=report.title,
        report_type=report.report_type,
        status=report.status,
        report_json=report.report_json,
    )


@router.get("/{report_id}/html", response_class=HTMLResponse)
def get_report_html(
    report_id: int,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    report = ReportRepository(session).get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found: {report_id}",
        )
    return HTMLResponse(report.rendered_html or "")


def _default_question(topic: str) -> str:
    return f"Generate a concise investment research brief about {topic.strip()}."


def _agent_result_from_run(session: Session, *, run_id: int) -> AgentLoopResult:
    repository = AgentRunRepository(session)
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source run not found: {run_id}",
        )
    if run.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot generate a report from an incomplete Ask run.",
        )

    metadata = run.metadata_json or {}
    answer = _stored_answer(session, run_id=run.id, metadata=metadata)
    if answer is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Cannot generate a report from this run because no source-backed "
                "answer or claim was stored. Ask the question again, then generate "
                "a report."
            ),
        )

    evidence_ids = _evidence_ids_from_metadata(metadata)
    sources = _sources_from_metadata(metadata, evidence_ids=evidence_ids)
    if not sources:
        sources = _sources_from_tool_calls(
            session,
            repository.list_tool_calls(run_id=run.id),
            evidence_ids=evidence_ids,
        )
    if is_no_evidence_answer(answer):
        evidence_ids = ()
        sources = ()

    return AgentLoopResult(
        run_id=run.id,
        run_key=run.run_key,
        status=run.status,
        answer=answer,
        evidence_ids=evidence_ids,
        sources=sources,
        iterations=_metadata_int(metadata, "iterations"),
        total_tokens=run.total_tokens,
        total_estimated_cost_usd=float(run.total_estimated_cost_usd),
        error_code=_metadata_string(metadata, "error_code"),
    )


def _evidence_ids_from_metadata(metadata: dict[str, Any]) -> tuple[int, ...]:
    values = metadata.get("evidence_ids")
    if not isinstance(values, list):
        return ()
    evidence_ids: list[int] = []
    for value in values:
        if isinstance(value, int) and value not in evidence_ids:
            evidence_ids.append(value)
    return tuple(evidence_ids)


def _stored_answer(
    session: Session,
    *,
    run_id: int,
    metadata: dict[str, Any],
) -> str | None:
    answer = metadata.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer

    claim = session.scalar(
        select(Claim)
        .where(Claim.run_id == run_id, Claim.report_id.is_(None))
        .order_by(Claim.created_at.asc(), Claim.id.asc())
    )
    if claim is None or not claim.claim_text.strip():
        return None
    return f"Based on the strongest local source, {claim.claim_text}"


def _sources_from_metadata(
    metadata: dict[str, Any],
    *,
    evidence_ids: tuple[int, ...],
) -> tuple[AgentEvidenceSource, ...]:
    raw_sources = metadata.get("answer_sources")
    if not isinstance(raw_sources, list):
        return ()
    allowed_ids = set(evidence_ids)
    sources: list[AgentEvidenceSource] = []
    seen: set[int] = set()
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, int) or evidence_id in seen:
            continue
        if allowed_ids and evidence_id not in allowed_ids:
            continue
        source_uri = item.get("source_uri")
        source_type = item.get("source_type")
        title = item.get("title")
        excerpt = item.get("excerpt")
        if not all(
            isinstance(value, str)
            for value in (source_uri, source_type, title, excerpt)
        ):
            continue
        display_name = item.get("display_name")
        page_or_section = item.get("page_or_section")
        sources.append(
            AgentEvidenceSource(
                evidence_id=evidence_id,
                display_name=(
                    display_name
                    if isinstance(display_name, str)
                    else source_display_name(source_uri) or title
                ),
                source_uri=source_uri,
                source_type=source_type,
                title=title,
                excerpt=excerpt,
                page_or_section=(
                    page_or_section if isinstance(page_or_section, str) else None
                ),
            )
        )
        seen.add(evidence_id)
    return tuple(sources)


def _sources_from_tool_calls(
    session: Session,
    tool_calls: object,
    *,
    evidence_ids: tuple[int, ...],
) -> tuple[AgentEvidenceSource, ...]:
    allowed_ids = set(evidence_ids)
    sources: list[AgentEvidenceSource] = []
    seen: set[int] = set()
    for tool_call in tool_calls:
        output = getattr(tool_call, "output_json", {})
        if not isinstance(output, dict):
            continue
        for result in output.get("results", []):
            if not isinstance(result, dict):
                continue
            evidence_id = result.get("evidence_item_id")
            if not isinstance(evidence_id, int):
                continue
            if evidence_id in seen or (allowed_ids and evidence_id not in allowed_ids):
                continue
            source_uri = result.get("source_uri")
            source_type = result.get("source_type")
            evidence = session.get(EvidenceItem, evidence_id)
            chunk_id = result.get("chunk_id")
            chunk = session.get(Chunk, chunk_id) if isinstance(chunk_id, int) else None
            if not isinstance(source_uri, str) and evidence is not None:
                source_uri = evidence.source_uri
            if not isinstance(source_type, str) and evidence is not None:
                source_type = evidence.source_type
            if not isinstance(source_uri, str) or not isinstance(source_type, str):
                continue
            title = result.get("title")
            if not isinstance(title, str) and evidence is not None:
                title = evidence.title
            if not isinstance(title, str):
                title = source_display_name(source_uri)
            page_or_section = result.get("page_or_section")
            if not isinstance(page_or_section, str) and evidence is not None:
                page_or_section = evidence.page_or_section
            excerpt = (
                chunk.text
                if chunk is not None
                else evidence.excerpt
                if evidence is not None
                else ""
            )
            sources.append(
                AgentEvidenceSource(
                    evidence_id=evidence_id,
                    display_name=source_display_name(source_uri) or title,
                    source_uri=source_uri,
                    source_type=source_type,
                    title=title,
                    excerpt=excerpt if isinstance(excerpt, str) else "",
                    page_or_section=(
                        page_or_section if isinstance(page_or_section, str) else None
                    ),
                )
            )
            seen.add(evidence_id)
    return tuple(sources)


def _metadata_int(metadata: dict[str, Any], key: str) -> int:
    value = metadata.get(key)
    return value if isinstance(value, int) else 0


def _metadata_string(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _can_generate_report(answer: str, claims: object) -> bool:
    return bool(claims) and not is_no_evidence_answer(answer)


def _report_response(
    *,
    report_id: int,
    title: str,
    report_type: str,
    status: str,
    report_json: dict[str, Any],
) -> ReportResponse:
    return ReportResponse(
        report_id=report_id,
        title=title,
        report_type=report_type,
        status=status,
        run_id=int(report_json.get("run_id", 0)),
        html_url=f"/reports/{report_id}/html",
        report_json=report_json,
    )
