from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
import re
from typing import Any

from sqlalchemy.orm import Session

from investment_agent.embeddings import EmbeddingProvider
from investment_agent.harness.types import ToolCall, ToolResult
from investment_agent.repositories import DocumentRepository
from investment_agent.retrieval.constants import (
    RETRIEVE_EVIDENCE_TOOL as RETRIEVE_EVIDENCE_TOOL,
)
from investment_agent.retrieval.hybrid import HybridRetrievalService
from investment_agent.retrieval.policy import (
    AdaptiveSearchService,
    EvidenceSlotSpec,
    search_result_metadata,
)
from investment_agent.retrieval.vector import RetrievalResult
from investment_agent.storage import EvidenceItem

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "been",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "might",
    "of",
    "on",
    "or",
    "say",
    "says",
    "should",
    "that",
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
_DOCUMENT_REFERENCE_TERMS = {
    "article",
    "document",
    "file",
    "paper",
    "pdf",
    "report",
    "source",
    "upload",
    "uploaded",
}
_CJK_DOCUMENT_REFERENCE_TERMS = (
    "这篇文章",
    "这篇报告",
    "这个文档",
    "这个文件",
    "上传的文章",
    "上传的报告",
    "上传的文档",
    "上传的文件",
)
_SEMANTIC_RELEVANCE_THRESHOLD = 0.62


def make_retrieve_evidence_tool(
    session: Session,
    embedding_provider: EmbeddingProvider,
    *,
    method_slots: tuple[EvidenceSlotSpec, ...] = (),
) -> Callable[[ToolCall], ToolResult]:
    def retrieve_evidence(call: ToolCall) -> ToolResult:
        try:
            query = _required_str(call.arguments, "query")
            top_k = _optional_positive_int(call.arguments.get("top_k"), default=5)
            document_id = _optional_positive_int_or_none(
                call.arguments.get("document_id"),
                field_name="document_id",
            )
            access_scope = _optional_str(call.arguments.get("access_scope"))
            as_of_date = _optional_date(call.arguments.get("as_of_date"))
            search_result = AdaptiveSearchService(
                HybridRetrievalService(session, embedding_provider)
            ).search(
                query,
                top_k=max(top_k, 10),
                document_id=document_id,
                access_scope=access_scope,
                as_of_date=as_of_date,
                method_slots=method_slots,
            )
            # AdaptiveSearchService returns only Evidence-Gate-accepted rows. Do
            # not apply a second relevance rule or an unverified document fallback
            # here; that previously made search, generation, and citations disagree.
            results = list(search_result.results)[:top_k]
            supported_passages = {
                item.result.chunk_id: item.supported_passage
                for item in search_result.evidence_gate.accepted
            }
        except (TypeError, ValueError) as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                error_code="invalid_arguments",
                output={"message": str(exc)},
                retryable=False,
            )

        return ToolResult(
            call_id=call.call_id,
            status="ok",
            output={
                "search": search_result_metadata(search_result),
                "results": [
                    {
                        "chunk_id": result.chunk_id,
                        "document_id": result.document_id,
                        "evidence_item_id": result.evidence_item_id,
                        "score": result.score,
                        "fused_score": result.fused_score,
                        "semantic_score": result.semantic_score,
                        "match_signals": list(result.match_signals),
                        "channel_ranks": dict(result.channel_ranks),
                        "text": result.text,
                        "context": result.context_text,
                        "supported_passage": supported_passages.get(result.chunk_id),
                        "source_uri": result.source_uri,
                        "source_type": result.source_type,
                        "title": result.title,
                        "page_or_section": result.page_or_section,
                        "evidence_grade": result.evidence_grade,
                        "excerpt": result.excerpt,
                        "publication_date": (
                            result.publication_date.isoformat()
                            if result.publication_date is not None
                            else None
                        ),
                        "data_as_of_date": (
                            result.data_as_of_date.isoformat()
                            if result.data_as_of_date is not None
                            else None
                        ),
                    }
                    for result in results
                ]
            },
        )

    return retrieve_evidence


def _required_str(arguments: Mapping[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string argument: {key}")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("access_scope must be a non-empty string")
    return value


def _optional_positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("top_k must be a positive integer")
    top_k = int(value)
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    return top_k


def _optional_positive_int_or_none(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    parsed_value = int(value)
    if parsed_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return parsed_value


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("as_of_date must be an ISO date string")


def _filter_results_by_local_relevance(
    query: str,
    results: list[RetrievalResult],
    *,
    allow_semantic_match: bool = False,
) -> list[RetrievalResult]:
    query_terms = _content_terms(query)
    if not query_terms:
        return results
    required_overlap = 1 if len(query_terms) <= 2 else 2
    filtered: list[RetrievalResult] = []
    for result in results:
        searchable_text = " ".join(
            part
            for part in (result.title, result.text, result.excerpt or "")
            if part
        )
        overlap = query_terms & _content_terms(searchable_text)
        result_overlap = 1 if _allows_broad_csv_intent(query, result) else required_overlap
        semantic_score = (
            result.semantic_score
            if result.semantic_score is not None
            else result.score
        )
        semantic_match = (
            allow_semantic_match
            and semantic_score is not None
            and semantic_score >= _SEMANTIC_RELEVANCE_THRESHOLD
        )
        if len(overlap) >= result_overlap or semantic_match:
            filtered.append(result)
    return filtered


def _allows_broad_csv_intent(query: str, result: RetrievalResult) -> bool:
    if result.source_type != "csv":
        return False
    query_terms = _content_terms(query)
    return bool(
        query_terms
        & {
            "affect",
            "driver",
            "factor",
            "influence",
            "price",
            "trend",
            "value",
        }
    )


def _references_current_document(query: str) -> bool:
    lowered = query.lower()
    if any(term in query for term in _CJK_DOCUMENT_REFERENCE_TERMS):
        return True
    query_terms = set(re.findall(r"[a-z0-9]+", lowered))
    return bool(query_terms & _DOCUMENT_REFERENCE_TERMS) and (
        "this" in query_terms
        or "current" in query_terms
        or "uploaded" in query_terms
    )


def _recent_document_results(
    session: Session,
    *,
    top_k: int,
    access_scope: str | None,
    as_of_date: date | None,
) -> list[RetrievalResult]:
    repository = DocumentRepository(session)
    for document in repository.list_documents():
        if access_scope is not None and document.access_scope != access_scope:
            continue
        document_results: list[RetrievalResult] = []
        for chunk in repository.list_chunks_for_document(document.id):
            evidence = (
                session.get(EvidenceItem, chunk.evidence_item_id)
                if chunk.evidence_item_id is not None
                else None
            )
            if not _evidence_allowed_by_date(evidence, as_of_date):
                continue
            document_results.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    evidence_item_id=evidence.id if evidence is not None else None,
                    score=0.0,
                    text=chunk.text,
                    source_uri=document.source_uri,
                    source_type=document.source_type,
                    title=document.title,
                    page_or_section=(
                        evidence.page_or_section if evidence is not None else None
                    ),
                    evidence_grade=(
                        evidence.evidence_grade if evidence is not None else None
                    ),
                    excerpt=evidence.excerpt if evidence is not None else None,
                )
            )
            if len(document_results) >= top_k:
                return document_results
        if document_results:
            return document_results
    return []


def _document_results(
    session: Session,
    *,
    document_id: int,
    top_k: int,
    access_scope: str | None,
    as_of_date: date | None,
) -> list[RetrievalResult]:
    repository = DocumentRepository(session)
    document = repository.get_document(document_id)
    if document is None:
        return []
    if access_scope is not None and document.access_scope != access_scope:
        return []

    results: list[RetrievalResult] = []
    for chunk in repository.list_chunks_for_document(document.id):
        evidence = (
            session.get(EvidenceItem, chunk.evidence_item_id)
            if chunk.evidence_item_id is not None
            else None
        )
        if not _evidence_allowed_by_date(evidence, as_of_date):
            continue
        results.append(
            RetrievalResult(
                chunk_id=chunk.id,
                document_id=document.id,
                evidence_item_id=evidence.id if evidence is not None else None,
                score=0.0,
                text=chunk.text,
                source_uri=document.source_uri,
                source_type=document.source_type,
                title=document.title,
                page_or_section=evidence.page_or_section if evidence is not None else None,
                evidence_grade=evidence.evidence_grade if evidence is not None else None,
                excerpt=evidence.excerpt if evidence is not None else None,
            )
        )
        if len(results) >= top_k:
            return results
    return results


def _evidence_allowed_by_date(
    evidence: EvidenceItem | None,
    as_of_date: date | None,
) -> bool:
    if evidence is None or as_of_date is None:
        return True
    if evidence.publication_date is not None and evidence.publication_date > as_of_date:
        return False
    if evidence.data_as_of_date is not None and evidence.data_as_of_date > as_of_date:
        return False
    return True


def _lexical_results(
    session: Session,
    *,
    query: str,
    document_id: int | None,
    access_scope: str | None,
    as_of_date: date | None,
    limit: int,
) -> list[RetrievalResult]:
    repository = DocumentRepository(session)
    documents = repository.list_documents()
    if document_id is not None:
        documents = [document for document in documents if document.id == document_id]

    ranked: list[RetrievalResult] = []
    for document in documents:
        if access_scope is not None and document.access_scope != access_scope:
            continue
        for chunk in repository.list_chunks_for_document(document.id):
            evidence = (
                session.get(EvidenceItem, chunk.evidence_item_id)
                if chunk.evidence_item_id is not None
                else None
            )
            if not _evidence_allowed_by_date(evidence, as_of_date):
                continue
            score = _lexical_score(
                query,
                title=document.title,
                text=chunk.text,
                excerpt=evidence.excerpt if evidence is not None else None,
            )
            if score <= 0:
                continue
            ranked.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    evidence_item_id=evidence.id if evidence is not None else None,
                    score=score,
                    text=chunk.text,
                    source_uri=document.source_uri,
                    source_type=document.source_type,
                    title=document.title,
                    page_or_section=(
                        evidence.page_or_section if evidence is not None else None
                    ),
                    evidence_grade=(
                        evidence.evidence_grade if evidence is not None else None
                    ),
                    excerpt=evidence.excerpt if evidence is not None else None,
                )
            )
    return sorted(ranked, key=lambda result: result.score, reverse=True)[:limit]


def _lexical_score(
    query: str,
    *,
    title: str,
    text: str,
    excerpt: str | None,
) -> float:
    query_terms = _ranking_terms(query) - _DOCUMENT_REFERENCE_TERMS - {
        "identify",
    }
    if not query_terms:
        return 0.0
    body_terms = _ranking_terms(" ".join(part for part in (text, excerpt or "") if part))
    overlap = query_terms & body_terms
    required_overlap = 1 if len(query_terms) <= 2 else 2
    if len(overlap) < required_overlap:
        return 0.0
    title_overlap = query_terms & _ranking_terms(title)
    coverage = len(overlap) / len(query_terms)
    title_bonus = min(0.1, len(title_overlap) * 0.025)
    phrase_bonus = 0.1 if _contains_query_phrase(query, text) else 0.0
    return min(1.0, 0.2 + 0.7 * coverage + title_bonus + phrase_bonus)


def _merge_ranked_results(
    *,
    semantic_results: list[RetrievalResult],
    lexical_results: list[RetrievalResult],
    limit: int,
) -> list[RetrievalResult]:
    combined: dict[int, RetrievalResult] = {
        result.chunk_id: result for result in semantic_results
    }
    for lexical in lexical_results:
        existing = combined.get(lexical.chunk_id)
        if existing is None or lexical.score > existing.score:
            combined[lexical.chunk_id] = lexical
    return sorted(combined.values(), key=lambda result: result.score, reverse=True)[:limit]


def _ranking_terms(value: str) -> set[str]:
    normalized: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if token in _STOPWORDS or len(token) <= 1:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            normalized.add(f"year:{token}")
            continue
        normalized.add(_normalize_ranking_term(token))
    for half, short_year in re.findall(r"\b([12]h)\s*[’']?(\d{2})\b", value.lower()):
        normalized.add(half)
        normalized.add(f"year:20{short_year}")
    return normalized


def _normalize_ranking_term(token: str) -> str:
    aliases = {
        "decline": "fall",
        "declined": "fall",
        "declines": "fall",
        "falling": "fall",
        "fell": "fall",
        "identified": "identify",
        "identifies": "identify",
        "prices": "price",
        "risks": "risk",
        "rates": "rate",
        "yields": "yield",
    }
    return aliases.get(token, token)


def _contains_query_phrase(query: str, text: str) -> bool:
    query_terms = [
        term
        for term in re.findall(r"[a-z0-9]+", query.lower())
        if term not in _STOPWORDS and len(term) > 2
    ]
    lowered_text = text.lower()
    return any(
        f"{left} {right}" in lowered_text
        for left, right in zip(query_terms, query_terms[1:])
    )


def _content_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }
