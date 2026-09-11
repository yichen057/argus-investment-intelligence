from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from investment_agent.config import Settings
from investment_agent.embeddings import DeterministicHashEmbeddingProvider
from investment_agent.repositories import (
    ChunkCreate,
    DocumentCreate,
    DocumentRepository,
    EvidenceItemCreate,
)
from investment_agent.retrieval.hybrid import (
    HybridRetrievalService,
    HybridSearchDiagnostics,
    HybridSearchResponse,
)
from investment_agent.retrieval.policy import (
    AdaptiveSearchService,
    DeterministicComplexityPolicy,
    EvidenceSlotSpec,
    SearchMode,
)
from investment_agent.retrieval.vector import RetrievalResult
from investment_agent.storage import Base, make_engine, make_session_factory


def _session_factory(tmp_path: Path) -> sessionmaker[Session]:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'adaptive-search.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_hybrid_retrieval_exposes_rrf_channels_and_neighbor_context(
    tmp_path: Path,
) -> None:
    factory = _session_factory(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)
    with factory() as session:
        repository = DocumentRepository(session)
        document = repository.create_document(
            DocumentCreate(
                source_uri="file:///gold.md",
                source_type="markdown",
                title="Gold outlook",
                content_hash="document",
            )
        )
        texts = (
            "Background: gold demand increased before the policy meeting.",
            "Gold downside risk rises when real interest rates turn higher.",
            "The next section describes monitoring and falsification checks.",
        )
        for index, text in enumerate(texts):
            evidence = repository.create_evidence_item(
                EvidenceItemCreate(
                    document_id=document.id,
                    source_uri=document.source_uri,
                    source_type=document.source_type,
                    title=document.title,
                    page_or_section=f"section {index + 1}",
                    evidence_grade="source",
                    excerpt=text,
                    content_hash=f"evidence-{index}",
                )
            )
            repository.create_chunk(
                ChunkCreate(
                    document_id=document.id,
                    evidence_item_id=evidence.id,
                    chunk_index=index,
                    text=text,
                    content_hash=f"chunk-{index}",
                )
            )

        response = HybridRetrievalService(session, provider).retrieve(
            "What downside risk does gold face when real interest rates rise?",
            top_k=1,
            document_id=document.id,
        )

    assert response.results[0].text == texts[1]
    assert {"exact", "full_text"} <= set(response.results[0].match_signals)
    assert response.results[0].fused_score is not None
    assert response.results[0].channel_ranks
    assert response.results[0].context_text is not None
    assert texts[0] in response.results[0].context_text
    assert texts[2] in response.results[0].context_text
    assert response.diagnostics.channel_counts["semantic"] == 0


def test_neighbor_context_does_not_leak_future_evidence(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)
    with factory() as session:
        repository = DocumentRepository(session)
        document = repository.create_document(
            DocumentCreate(
                source_uri="file:///timeline.md",
                source_type="markdown",
                title="Timeline",
                content_hash="timeline-document",
            )
        )
        for index, (text, evidence_date) in enumerate(
            (
                ("Gold risk evidence was available in 2024.", date(2024, 6, 30)),
                ("Future 2027 policy outcome must stay hidden.", date(2027, 1, 1)),
            )
        ):
            evidence = repository.create_evidence_item(
                EvidenceItemCreate(
                    document_id=document.id,
                    source_uri=document.source_uri,
                    source_type=document.source_type,
                    title=document.title,
                    page_or_section=f"section {index + 1}",
                    evidence_grade="source",
                    excerpt=text,
                    content_hash=f"timeline-evidence-{index}",
                    publication_date=evidence_date,
                    data_as_of_date=evidence_date,
                )
            )
            repository.create_chunk(
                ChunkCreate(
                    document_id=document.id,
                    evidence_item_id=evidence.id,
                    chunk_index=index,
                    text=text,
                    content_hash=f"timeline-chunk-{index}",
                )
            )

        response = HybridRetrievalService(session, provider).retrieve(
            "Gold risk evidence 2024",
            top_k=1,
            document_id=document.id,
            as_of_date=date(2025, 1, 1),
        )

    assert response.results[0].context_text is not None
    assert "available in 2024" in response.results[0].context_text
    assert "Future 2027" not in response.results[0].context_text


def test_deterministic_policy_keeps_direct_lookup_fast() -> None:
    plan = DeterministicComplexityPolicy().plan("What did the report say about GLD?")

    assert plan.mode is SearchMode.FAST
    assert plan.max_queries == 1
    assert [slot.slot_id for slot in plan.required_slots] == ["primary_evidence"]


def test_adaptive_search_escalates_complex_question_with_hard_query_cap() -> None:
    retriever = _FakeRetriever()
    service = AdaptiveSearchService(retriever)  # type: ignore[arg-type]

    result = service.search(
        "Compare the latest downside risks and recommend which portfolio approach fits.",
        top_k=5,
        document_id=None,
        access_scope=None,
        as_of_date=date(2026, 7, 16),
    )

    assert result.plan.mode is SearchMode.DEEP
    assert result.agent_search_triggered is True
    assert len(result.queries) == result.plan.max_queries == 2
    assert len({trace.query for trace in result.queries}) == len(result.queries)
    assert result.evidence_gate.decision.value == "refuse"
    assert result.evidence_gate.material_gaps
    assert result.stop_reason == "evidence_gate_refused_after_follow_up"


def test_method_slots_are_query_hints_and_do_not_override_fast_budget() -> None:
    method_slot = EvidenceSlotSpec(
        slot_id="industry_bottleneck",
        description="Evidence for a constrained industry-chain node.",
        search_terms=("capacity", "bottleneck"),
        query_template="industry bottleneck capacity {question}",
    )
    retriever = _FakeRetriever()

    result = AdaptiveSearchService(retriever).search(  # type: ignore[arg-type]
        "Summarize ACME.",
        top_k=3,
        document_id=None,
        access_scope=None,
        as_of_date=None,
        method_slots=(method_slot,),
    )

    assert result.plan.mode is SearchMode.FAST
    assert [slot.slot_id for slot in result.plan.method_hints] == [
        "industry_bottleneck"
    ]
    assert "industry_bottleneck" not in result.coverage.missing_slots
    assert result.agent_search_triggered is False
    assert len(result.queries) == 1
    assert result.stop_reason.startswith("evidence_gate_")


def test_agent_search_does_not_repeat_equivalent_gap_queries() -> None:
    shared_template = "missing evidence for {question}"
    slots = (
        EvidenceSlotSpec(
            slot_id="capacity_constraint",
            description="Evidence for constrained production capacity.",
            search_terms=("not-present-capacity",),
            query_template=shared_template,
        ),
        EvidenceSlotSpec(
            slot_id="supplier_constraint",
            description="Evidence for constrained supplier availability.",
            search_terms=("not-present-supplier",),
            query_template=shared_template,
        ),
    )

    result = AdaptiveSearchService(_FakeRetriever()).search(  # type: ignore[arg-type]
        "Why compare two approaches?",
        top_k=3,
        document_id=None,
        access_scope=None,
        as_of_date=None,
        method_slots=slots,
    )

    assert result.agent_search_triggered is True
    expected_gap_query = shared_template.format(question="Why compare two approaches?")
    assert sum(trace.query == expected_gap_query for trace in result.queries) == 1
    assert len({trace.query.lower() for trace in result.queries}) == len(result.queries)


class _FakeRetriever:
    def retrieve(self, query: str, **kwargs) -> HybridSearchResponse:
        del kwargs
        lowered = query.lower()
        if "comparison" in lowered:
            rows = (
                _result(2, 2, "Comparable portfolio evidence for a second approach."),
            )
        elif "latest current" in lowered:
            rows = (
                _result(
                    3,
                    1,
                    "Current market evidence is dated and directly relevant.",
                    data_as_of_date=date(2026, 7, 15),
                ),
            )
        elif "risks downside" in lowered:
            rows = (_result(4, 1, "The downside risk is an uncertain earnings path."),)
        elif "counter evidence" in lowered:
            rows = (_result(5, 2, "However, counter evidence challenges the thesis."),)
        else:
            rows = (_result(1, 1, "Primary evidence supports the initial summary."),)
        return HybridSearchResponse(
            results=rows,
            diagnostics=HybridSearchDiagnostics(
                channel_counts={"exact": 1, "full_text": 1, "semantic": 0},
                candidate_pool=20,
                rrf_k=60,
                weights={"exact": 3.0, "full_text": 1.0, "semantic": 1.0},
            ),
        )


def _result(
    chunk_id: int,
    document_id: int,
    text: str,
    *,
    data_as_of_date: date | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=document_id,
        evidence_item_id=chunk_id,
        score=0.8,
        text=text,
        source_uri=f"file:///{document_id}.md",
        source_type="markdown",
        title=f"Document {document_id}",
        page_or_section=None,
        evidence_grade="source",
        excerpt=text,
        data_as_of_date=data_as_of_date,
        fused_score=0.03,
        match_signals=("exact", "full_text"),
    )
