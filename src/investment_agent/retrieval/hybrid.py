from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date
import math
import re

from sqlalchemy.orm import Session

from investment_agent.embeddings import EmbeddingProvider
from investment_agent.repositories.documents import DocumentRepository
from investment_agent.retrieval.evidence_gate import is_document_summary_query
from investment_agent.storage.models import Chunk, Document, EvidenceItem
from investment_agent.retrieval.vector import RetrievalResult, VectorRetrievalService


RRF_K = 60
DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {
    "exact": 3.0,
    "full_text": 1.0,
    "semantic": 1.0,
    "document_summary": 1.0,
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "can",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "which",
    "who",
    "why",
    "with",
}

_ALIASES = {
    "decline": "fall",
    "declined": "fall",
    "declines": "fall",
    "falling": "fall",
    "fell": "fall",
    "identified": "identify",
    "identifies": "identify",
    "prices": "price",
    "rates": "rate",
    "risks": "risk",
    "yields": "yield",
}


@dataclass(frozen=True)
class HybridSearchDiagnostics:
    channel_counts: dict[str, int]
    candidate_pool: int
    rrf_k: int
    weights: dict[str, float]


@dataclass(frozen=True)
class HybridSearchResponse:
    results: tuple[RetrievalResult, ...]
    diagnostics: HybridSearchDiagnostics


class HybridRetrievalService:
    """Fuse exact, lexical, and semantic rankings without mixing raw scores."""

    def __init__(
        self,
        session: Session,
        embedding_provider: EmbeddingProvider,
        *,
        channel_weights: dict[str, float] | None = None,
        rrf_k: int = RRF_K,
    ) -> None:
        if rrf_k <= 0:
            raise ValueError("RRF k must be positive")
        self._session = session
        self._repository = DocumentRepository(session)
        self._embedding_provider = embedding_provider
        self._weights = dict(channel_weights or DEFAULT_CHANNEL_WEIGHTS)
        self._rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        candidate_pool: int | None = None,
        document_id: int | None = None,
        access_scope: str | None = None,
        as_of_date: date | None = None,
        neighbor_window: int = 1,
    ) -> HybridSearchResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Query cannot be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if neighbor_window < 0 or neighbor_window > 2:
            raise ValueError("neighbor_window must be between 0 and 2")
        pool = candidate_pool or max(20, top_k * 4)
        if pool < top_k:
            pool = top_k

        exact = self._exact_results(
            normalized_query,
            limit=pool,
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )
        full_text = self._full_text_results(
            normalized_query,
            limit=pool,
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )
        semantic = (
            []
            if self._embedding_provider.provider_name == "local"
            else VectorRetrievalService(
                self._session,
                self._embedding_provider,
            ).retrieve(
                normalized_query,
                top_k=pool,
                document_id=document_id,
                access_scope=access_scope,
                as_of_date=as_of_date,
            )
        )
        document_summary = self._document_summary_results(
            normalized_query,
            limit=pool,
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )
        fused = _rrf_fuse(
            {
                "exact": exact,
                "full_text": full_text,
                "semantic": semantic,
                "document_summary": document_summary,
            },
            weights=self._weights,
            rrf_k=self._rrf_k,
        )
        deduplicated = _deduplicate_results(fused)
        expanded = tuple(
            self._with_neighbor_context(
                result,
                window=neighbor_window,
                as_of_date=as_of_date,
            )
            for result in deduplicated[:top_k]
        )
        return HybridSearchResponse(
            results=expanded,
            diagnostics=HybridSearchDiagnostics(
                channel_counts={
                    "exact": len(exact),
                    "full_text": len(full_text),
                    "semantic": len(semantic),
                    "document_summary": len(document_summary),
                },
                candidate_pool=pool,
                rrf_k=self._rrf_k,
                weights=dict(self._weights),
            ),
        )

    def _document_summary_results(
        self,
        query: str,
        *,
        limit: int,
        document_id: int | None,
        access_scope: str | None,
        as_of_date: date | None,
    ) -> list[RetrievalResult]:
        """Return bounded, representative chunks for an unambiguous summary request.

        This channel intentionally works without semantic embeddings. It activates only
        when one document is explicitly selected or the filtered library contains one
        document, preventing a vague "summarize" request from silently mixing files.
        """

        if not is_document_summary_query(query):
            return []
        records = self._repository.list_chunk_records(
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )
        document_ids = {document.id for _, _, document in records}
        if len(document_ids) != 1:
            return []
        usable = [
            record
            for record in records
            if len(" ".join(record[0].text.split())) >= 40
        ]
        if not usable:
            return []
        sample_size = min(max(1, limit), len(usable))
        if sample_size == 1:
            sampled = [usable[0]]
        else:
            indexes = {
                round(index * (len(usable) - 1) / (sample_size - 1))
                for index in range(sample_size)
            }
            sampled = [usable[index] for index in sorted(indexes)]
        return [
            _result_from_record(
                chunk,
                evidence,
                document,
                score=max(0.1, 1.0 - rank / max(1, len(sampled))),
                signal="document_summary",
            )
            for rank, (chunk, evidence, document) in enumerate(sampled)
        ]

    def _exact_results(
        self,
        query: str,
        *,
        limit: int,
        document_id: int | None,
        access_scope: str | None,
        as_of_date: date | None,
    ) -> list[RetrievalResult]:
        anchors = _exact_anchors(query)
        if not anchors:
            return []
        ranked: list[tuple[float, RetrievalResult]] = []
        for chunk, evidence, document in self._repository.list_chunk_records(
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        ):
            body_searchable = _normalized_search_text(
                " ".join((chunk.text, evidence.excerpt if evidence else ""))
            )
            matched = [anchor for anchor in anchors if anchor in body_searchable]
            if not matched:
                continue
            coverage = len(matched) / len(anchors)
            identifier_bonus = sum(
                0.15 for anchor in matched if re.search(r"\d", anchor)
            )
            phrase_bonus = max((len(anchor.split()) for anchor in matched), default=1)
            title_matches = sum(
                anchor in _normalized_search_text(document.title) for anchor in anchors
            )
            title_bonus = min(0.15, title_matches * 0.025)
            score = (
                coverage
                + identifier_bonus
                + min(0.25, phrase_bonus * 0.05)
                + title_bonus
            )
            ranked.append(
                (
                    score,
                    _result_from_record(
                        chunk,
                        evidence,
                        document,
                        score=score,
                        signal="exact",
                    ),
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [result for _, result in ranked[:limit]]

    def _full_text_results(
        self,
        query: str,
        *,
        limit: int,
        document_id: int | None,
        access_scope: str | None,
        as_of_date: date | None,
    ) -> list[RetrievalResult]:
        if self._session.get_bind().dialect.name == "postgresql":
            rows = self._repository.search_chunks_full_text_postgresql(
                query=_postgres_websearch_query(query),
                top_k=limit,
                document_id=document_id,
                access_scope=access_scope,
                as_of_date=as_of_date,
            )
            return [
                _result_from_record(
                    chunk,
                    evidence,
                    document,
                    score=score,
                    signal="full_text",
                )
                for chunk, evidence, document, score in rows
            ]
        return self._portable_full_text_results(
            query,
            limit=limit,
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )

    def _portable_full_text_results(
        self,
        query: str,
        *,
        limit: int,
        document_id: int | None,
        access_scope: str | None,
        as_of_date: date | None,
    ) -> list[RetrievalResult]:
        records = self._repository.list_chunk_records(
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )
        query_terms = _terms(query)
        if not query_terms:
            return []
        document_frequency: Counter[str] = Counter()
        record_terms: list[tuple[Chunk, EvidenceItem | None, Document, Counter[str]]] = []
        for chunk, evidence, document in records:
            terms = Counter(
                _term_sequence(
                    " ".join(
                        (
                            document.title,
                            chunk.text,
                            evidence.excerpt if evidence else "",
                        )
                    )
                )
            )
            record_terms.append((chunk, evidence, document, terms))
            document_frequency.update(set(terms))

        ranked: list[tuple[float, RetrievalResult]] = []
        corpus_size = max(1, len(record_terms))
        required_overlap = 1 if len(query_terms) <= 2 else 2
        for chunk, evidence, document, terms in record_terms:
            overlap = query_terms & set(terms)
            record_required_overlap = (
                1
                if document.source_type == "csv"
                and query_terms
                & {
                    "affect",
                    "driver",
                    "factor",
                    "influence",
                    "price",
                    "trend",
                    "value",
                }
                else required_overlap
            )
            if len(overlap) < record_required_overlap:
                continue
            score = 0.0
            for term in overlap:
                inverse_document_frequency = math.log(
                    1 + corpus_size / (1 + document_frequency[term])
                )
                score += (1 + math.log(terms[term])) * inverse_document_frequency
            score *= len(overlap) / len(query_terms)
            title_overlap = query_terms & _terms(document.title)
            score += 0.15 * len(title_overlap)
            if _contains_query_phrase(query, chunk.text):
                score += 0.25
            ranked.append(
                (
                    score,
                    _result_from_record(
                        chunk,
                        evidence,
                        document,
                        score=score,
                        signal="full_text",
                    ),
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [result for _, result in ranked[:limit]]

    def _with_neighbor_context(
        self,
        result: RetrievalResult,
        *,
        window: int,
        as_of_date: date | None,
    ) -> RetrievalResult:
        if window == 0:
            return replace(result, context_text=result.text)
        anchor = self._session.get(Chunk, result.chunk_id)
        if anchor is None:
            return result
        neighbors = self._repository.list_neighbor_chunks(
            document_id=result.document_id,
            chunk_index=anchor.chunk_index,
            window=window,
            as_of_date=as_of_date,
        )
        context = "\n\n".join(chunk.text for chunk in neighbors).strip()
        return replace(result, context_text=context[:6000] or result.text)


def _rrf_fuse(
    rankings: dict[str, list[RetrievalResult]],
    *,
    weights: dict[str, float],
    rrf_k: int,
) -> list[RetrievalResult]:
    scores: defaultdict[int, float] = defaultdict(float)
    ranks: defaultdict[int, dict[str, int]] = defaultdict(dict)
    candidates: dict[int, RetrievalResult] = {}
    semantic_scores: dict[int, float] = {}
    for channel, results in rankings.items():
        weight = weights.get(channel, 1.0)
        for rank, result in enumerate(results, start=1):
            scores[result.chunk_id] += weight / (rrf_k + rank)
            ranks[result.chunk_id][channel] = rank
            candidates.setdefault(result.chunk_id, result)
            if channel == "semantic":
                semantic_scores[result.chunk_id] = (
                    result.semantic_score
                    if result.semantic_score is not None
                    else result.score
                )
    maximum_score = sum(
        weight / (rrf_k + 1) for weight in weights.values() if weight > 0
    )
    fused: list[RetrievalResult] = []
    for chunk_id, raw_score in scores.items():
        channel_ranks = tuple(sorted(ranks[chunk_id].items()))
        normalized_score = raw_score / maximum_score if maximum_score else 0.0
        fused.append(
            replace(
                candidates[chunk_id],
                score=normalized_score,
                fused_score=raw_score,
                semantic_score=semantic_scores.get(chunk_id),
                match_signals=tuple(channel for channel, _ in channel_ranks),
                channel_ranks=channel_ranks,
            )
        )
    return sorted(
        fused,
        key=lambda result: (
            -(result.fused_score or 0.0),
            -len(result.match_signals),
            result.chunk_id,
        ),
    )


def _deduplicate_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    deduplicated: list[RetrievalResult] = []
    seen: set[tuple[int, str]] = set()
    for result in results:
        normalized = re.sub(r"\W+", " ", result.text.lower()).strip()
        key = (result.document_id, normalized)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(result)
    return deduplicated


def _result_from_record(
    chunk: Chunk,
    evidence: EvidenceItem | None,
    document: Document,
    *,
    score: float,
    signal: str,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk.id,
        document_id=document.id,
        evidence_item_id=evidence.id if evidence is not None else None,
        score=score,
        text=chunk.text,
        source_uri=document.source_uri,
        source_type=document.source_type,
        title=document.title,
        page_or_section=evidence.page_or_section if evidence is not None else None,
        evidence_grade=evidence.evidence_grade if evidence is not None else None,
        excerpt=evidence.excerpt if evidence is not None else None,
        publication_date=evidence.publication_date if evidence is not None else None,
        data_as_of_date=evidence.data_as_of_date if evidence is not None else None,
        match_signals=(signal,),
    )


def _exact_anchors(query: str) -> tuple[str, ...]:
    lowered = _normalized_search_text(query)
    anchors: list[str] = []
    anchors.extend(
        _normalized_search_text(match)
        for match in re.findall(r"[\"“”']([^\"“”']{2,80})[\"“”']", query)
    )
    anchors.extend(re.findall(r"\b(?:19|20)\d{2}\b", lowered))
    anchors.extend(re.findall(r"\b\d+(?:\.\d+)?%\b", lowered))
    anchors.extend(token.lower() for token in re.findall(r"\b[A-Z]{2,6}\b", query))
    words = [term for term in _term_sequence(query) if not term.startswith("cjk:")]
    anchors.extend(" ".join(words[index : index + 2]) for index in range(len(words) - 1))
    anchors.extend(term[4:] for term in _terms(query) if term.startswith("cjk:"))
    return tuple(dict.fromkeys(anchor for anchor in anchors if len(anchor) > 1))


def _normalized_search_text(value: str) -> str:
    value = value.lower().replace("’", "'")
    value = re.sub(r"\b([12])h\s*'?([0-9]{2})\b", r"\1h 20\2", value)
    return re.sub(r"\s+", " ", value).strip()


def _postgres_websearch_query(value: str) -> str:
    tokens = [
        term.split(":", 1)[-1]
        for term in _term_sequence(value)
        if re.fullmatch(r"(?:year:|cjk:)?[a-z0-9\u3400-\u9fff]+", term)
    ]
    return " OR ".join(dict.fromkeys(tokens)) or value


def _terms(value: str) -> set[str]:
    return set(_term_sequence(value))


def _term_sequence(value: str) -> list[str]:
    terms: list[str] = []
    lowered = _normalized_search_text(value)
    for token in re.findall(r"[a-z0-9]+", lowered):
        if token in _STOPWORDS or len(token) <= 1:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            terms.append(f"year:{token}")
        else:
            terms.append(_ALIASES.get(token, token))
    for sequence in re.findall(r"[\u3400-\u9fff]{2,}", value):
        if len(sequence) <= 4:
            terms.append(f"cjk:{sequence}")
        terms.extend(
            f"cjk:{sequence[index:index + 2]}" for index in range(len(sequence) - 1)
        )
    return terms


def _contains_query_phrase(query: str, text: str) -> bool:
    query_terms = [
        term for term in _term_sequence(query) if not term.startswith(("year:", "cjk:"))
    ]
    lowered_text = _normalized_search_text(text)
    return any(
        f"{left} {right}" in lowered_text
        for left, right in zip(query_terms, query_terms[1:])
    )
