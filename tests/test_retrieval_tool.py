from __future__ import annotations

from pathlib import Path
from time import sleep

import pytest
from sqlalchemy.orm import Session, sessionmaker

from investment_agent.config import Settings
from investment_agent.embeddings import DeterministicHashEmbeddingProvider, EmbeddingService
from investment_agent.harness import (
    ToolCall,
    ToolExecutionPolicy,
    ToolRegistry,
    ToolResult,
)
from investment_agent.ingestion import LocalFileIngestor
from investment_agent.retrieval.tool import (
    RETRIEVE_EVIDENCE_TOOL,
    _filter_results_by_local_relevance,
    make_retrieve_evidence_tool,
)
from investment_agent.retrieval.vector import RetrievalResult, VectorRetrievalService
from investment_agent.repositories import (
    ChunkCreate,
    DocumentCreate,
    DocumentRepository,
    EvidenceItemCreate,
)
from investment_agent.storage import Base, make_engine, make_session_factory


def sqlite_settings(database_url: str) -> Settings:
    return Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=database_url,
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )


def session_factory_for_tmp_db(tmp_path: Path) -> sessionmaker[Session]:
    settings = sqlite_settings(f"sqlite:///{tmp_path / 'argus.db'}")
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_tool_registry_returns_unknown_tool_error() -> None:
    registry = ToolRegistry()

    result = registry.dispatch(
        ToolCall(call_id="call-1", name="missing_tool", arguments={})
    )

    assert result.status == "error"
    assert result.error_code == "unknown_tool"
    assert result.retryable is False


def test_tool_registry_rejects_empty_or_duplicate_tool_names() -> None:
    registry = ToolRegistry()

    def handler(call: ToolCall) -> ToolResult:
        return ToolResult(call_id=call.call_id, status="ok")

    registry.register("demo", handler)

    with pytest.raises(ValueError) as empty_exc:
        registry.register("", handler)
    assert str(empty_exc.value) == "Tool name cannot be empty"

    with pytest.raises(ValueError) as duplicate_exc:
        registry.register("demo", handler)
    assert str(duplicate_exc.value) == "Tool already registered: demo"


def test_tool_registry_retries_retryable_result_until_success() -> None:
    attempts = 0
    registry = ToolRegistry(
        policy=ToolExecutionPolicy(
            timeout_seconds=1,
            max_attempts=3,
            retry_backoff_seconds=0,
        )
    )

    def flaky_handler(call: ToolCall) -> ToolResult:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                error_code="temporary_failure",
                retryable=True,
            )
        return ToolResult(call_id=call.call_id, status="ok", output={"value": 42})

    registry.register("flaky", flaky_handler)
    result = registry.dispatch(ToolCall(call_id="call-1", name="flaky", arguments={}))

    assert result.status == "ok"
    assert attempts == 3
    assert result.output["value"] == 42
    assert result.output["_execution"]["attempts"] == 3


def test_tool_registry_times_out_with_bounded_attempts() -> None:
    attempts = 0
    registry = ToolRegistry(
        policy=ToolExecutionPolicy(
            timeout_seconds=0.01,
            max_attempts=2,
            retry_backoff_seconds=0,
        )
    )

    def slow_handler(call: ToolCall) -> ToolResult:
        nonlocal attempts
        attempts += 1
        sleep(0.05)
        return ToolResult(call_id=call.call_id, status="ok")

    registry.register("slow", slow_handler)
    result = registry.dispatch(ToolCall(call_id="call-1", name="slow", arguments={}))

    assert result.status == "error"
    assert result.error_code == "tool_timeout"
    assert result.retryable is False
    assert result.output["_execution"]["attempts"] == 2
    assert attempts == 2


def test_retrieve_evidence_tool_returns_ranked_evidence(tmp_path: Path) -> None:
    gold = tmp_path / "gold.md"
    supply = tmp_path / "supply.txt"
    gold.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    supply.write_text(
        "Supplier capacity normalized and ACME backlog declined.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        gold_result = LocalFileIngestor(session).ingest_path(gold)
        supply_result = LocalFileIngestor(session).ingest_path(supply)
        embedding_service = EmbeddingService(session, provider)
        embedding_service.embed_document_chunks(gold_result.document_id)
        embedding_service.embed_document_chunks(supply_result.document_id)

        registry = ToolRegistry()
        registry.register(
            RETRIEVE_EVIDENCE_TOOL,
            make_retrieve_evidence_tool(session, provider),
        )

        result = registry.dispatch(
            ToolCall(
                call_id="call-1",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": "gold real yields central banks",
                    "top_k": 1,
                    "as_of_date": "2026-01-01",
                },
            )
        )

    assert result.status == "ok"
    results = result.output["results"]
    assert len(results) == 1
    assert results[0]["title"] == "gold"
    assert "Gold demand strengthened" in results[0]["text"]
    assert "Gold demand strengthened" in results[0]["supported_passage"]
    assert results[0]["evidence_grade"] == "source"
    assert isinstance(results[0]["score"], float)
    assert result.output["search"]["evidence_gate"]["decision"] == "supported"
    assert result.output["search"]["accepted_evidence_ids"] == [
        results[0]["evidence_item_id"]
    ]


def test_retrieve_evidence_tool_rejects_invalid_arguments(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        tool = make_retrieve_evidence_tool(session, provider)
        result = tool(
            ToolCall(
                call_id="call-1",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={"top_k": 0},
            )
        )

    assert result.status == "error"
    assert result.error_code == "invalid_arguments"
    assert result.retryable is False


def test_retrieve_evidence_tool_filters_unrelated_local_fallback_result(
    tmp_path: Path,
) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        result = LocalFileIngestor(session).ingest_path(source)
        EmbeddingService(session, provider).embed_document_chunks(result.document_id)
        tool = make_retrieve_evidence_tool(session, provider)
        tool_result = tool(
            ToolCall(
                call_id="call-1",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": "What does ACME revenue say about software margins?",
                    "top_k": 3,
                },
            )
        )

    assert tool_result.status == "ok"
    assert tool_result.output["results"] == []


def test_retrieve_evidence_tool_falls_back_to_recent_document_for_this_article(
    tmp_path: Path,
) -> None:
    old_source = tmp_path / "old_macro.md"
    current_article = tmp_path / "gold_outlook_zh.md"
    old_source.write_text(
        "Supplier capacity normalized and ACME backlog declined.",
        encoding="utf-8",
    )
    current_article.write_text(
        "黄金展望指出，2026 年金价可能受到央行购金、实际利率变化和投资需求影响。",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        old_result = LocalFileIngestor(session).ingest_path(old_source)
        article_result = LocalFileIngestor(session).ingest_path(current_article)
        embedding_service = EmbeddingService(session, provider)
        embedding_service.embed_document_chunks(old_result.document_id)
        embedding_service.embed_document_chunks(article_result.document_id)
        tool = make_retrieve_evidence_tool(session, provider)
        tool_result = tool(
            ToolCall(
                call_id="call-1",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": "Based on this article, can I invest gold in 2026?",
                    "top_k": 3,
                },
            )
        )

    assert tool_result.status == "ok"
    results = tool_result.output["results"]
    assert len(results) == 1
    assert results[0]["title"] == "gold_outlook_zh"
    assert "黄金展望" in results[0]["text"]


def test_retrieve_evidence_tool_uses_selected_document_context(
    tmp_path: Path,
) -> None:
    old_source = tmp_path / "old_macro.md"
    current_article = tmp_path / "gold_outlook_zh.md"
    old_source.write_text(
        "Supplier capacity normalized and ACME backlog declined.",
        encoding="utf-8",
    )
    current_article.write_text(
        "黄金展望指出，2026 年金价可能受到央行购金、实际利率变化和投资需求影响。",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        old_result = LocalFileIngestor(session).ingest_path(old_source)
        article_result = LocalFileIngestor(session).ingest_path(current_article)
        embedding_service = EmbeddingService(session, provider)
        embedding_service.embed_document_chunks(old_result.document_id)
        embedding_service.embed_document_chunks(article_result.document_id)
        tool = make_retrieve_evidence_tool(session, provider)
        tool_result = tool(
            ToolCall(
                call_id="call-1",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": "Can I invest gold in 2026?",
                    "document_id": article_result.document_id,
                    "top_k": 3,
                },
            )
        )

    assert tool_result.status == "ok"
    results = tool_result.output["results"]
    assert len(results) == 1
    assert results[0]["title"] == "gold_outlook_zh"
    assert "黄金展望" in results[0]["text"]


def test_selected_document_does_not_force_unrelated_evidence(tmp_path: Path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        result = LocalFileIngestor(session).ingest_path(source)
        EmbeddingService(session, provider).embed_document_chunks(result.document_id)
        tool = make_retrieve_evidence_tool(session, provider)
        tool_result = tool(
            ToolCall(
                call_id="call-1",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": "What are semiconductor software margins?",
                    "document_id": result.document_id,
                    "top_k": 3,
                },
            )
        )

    assert tool_result.status == "ok"
    assert tool_result.output["results"] == []


def test_semantic_score_can_pass_when_exact_words_do_not_overlap() -> None:
    related = RetrievalResult(
        chunk_id=1,
        document_id=1,
        evidence_item_id=1,
        score=0.69,
        text="Lower real yields reduce the opportunity cost of holding gold.",
        source_uri="file:///gold.md",
        source_type="markdown",
        title="Gold and Real Yields",
        page_or_section=None,
        evidence_grade="B",
        excerpt=None,
    )
    unrelated = RetrievalResult(
        chunk_id=2,
        document_id=1,
        evidence_item_id=1,
        score=0.56,
        text=related.text,
        source_uri=related.source_uri,
        source_type=related.source_type,
        title=related.title,
        page_or_section=None,
        evidence_grade="B",
        excerpt=None,
    )

    assert _filter_results_by_local_relevance(
        "What factors can influence gold prices?",
        [related],
        allow_semantic_match=True,
    ) == [related]
    assert _filter_results_by_local_relevance(
        "What affects semiconductor margins?",
        [unrelated],
        allow_semantic_match=True,
    ) == []


def test_selected_document_hybrid_search_recovers_exact_chunk_outside_vector_top_k(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        repository = DocumentRepository(session)
        document = repository.create_document(
            DocumentCreate(
                source_uri="file:///gold-outlook-2026.pdf",
                source_type="pdf",
                title="Gold outlook 2026",
                content_hash="sha256:hybrid-document",
            )
        )
        distractor_evidence = repository.create_evidence_item(
            EvidenceItemCreate(
                document_id=document.id,
                source_uri=document.source_uri,
                source_type=document.source_type,
                title=document.title,
                page_or_section="page 5",
                evidence_grade="source",
                excerpt="Gold demand and supply scenarios for 2026.",
                content_hash="sha256:distractor-evidence",
            )
        )
        distractor = repository.create_chunk(
            ChunkCreate(
                document_id=document.id,
                evidence_item_id=distractor_evidence.id,
                chunk_index=0,
                text="Gold demand and supply scenarios for 2026.",
                content_hash="sha256:distractor-chunk",
            )
        )
        target_evidence = repository.create_evidence_item(
            EvidenceItemCreate(
                document_id=document.id,
                source_uri=document.source_uri,
                source_type=document.source_type,
                title=document.title,
                page_or_section="page 17",
                evidence_grade="source",
                excerpt="A turn higher in growth and real rates presents downside risks.",
                content_hash="sha256:target-evidence",
            )
        )
        target = repository.create_chunk(
            ChunkCreate(
                document_id=document.id,
                evidence_item_id=target_evidence.id,
                chunk_index=1,
                text=(
                    "A turn higher in US growth sentiment, bottoming real interest rates, "
                    "and lower geopolitical risks present major gold downside risks during "
                    "2H'26."
                ),
                content_hash="sha256:target-chunk",
            )
        )

        monkeypatch.setattr(
            VectorRetrievalService,
            "retrieve",
            lambda self, query, **kwargs: [
                RetrievalResult(
                    chunk_id=distractor.id,
                    document_id=document.id,
                    evidence_item_id=distractor_evidence.id,
                    score=0.91,
                    text=distractor.text,
                    source_uri=document.source_uri,
                    source_type=document.source_type,
                    title=document.title,
                    page_or_section="page 5",
                    evidence_grade="source",
                    excerpt=distractor_evidence.excerpt,
                )
            ],
        )
        result = make_retrieve_evidence_tool(session, provider)(
            ToolCall(
                call_id="call-hybrid",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": (
                        "What downside risks does the report identify for gold in 2H 2026?"
                    ),
                    "document_id": document.id,
                    "top_k": 1,
                },
            )
        )

    assert result.status == "ok"
    assert result.output["results"][0]["chunk_id"] == target.id
    assert result.output["results"][0]["page_or_section"] == "page 17"


def test_explicit_chinese_summary_request_samples_single_english_document(
    tmp_path: Path,
) -> None:
    source = tmp_path / "meta_culture_reset.md"
    source.write_text(
        " ".join(
            [
                "Meta's infrastructure organization needs a culture reset because unclear ownership slows decisions.",
                "The document recommends explicit decision rights, measurable operating goals, and accountable leaders.",
                "It also argues that incentives should reward durable infrastructure outcomes instead of visible launches alone.",
            ]
            * 8
        ),
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_factory() as session:
        ingested = LocalFileIngestor(session).ingest_path(source)
        EmbeddingService(session, provider).embed_document_chunks(ingested.document_id)
        tool_result = make_retrieve_evidence_tool(session, provider)(
            ToolCall(
                call_id="call-summary",
                name=RETRIEVE_EVIDENCE_TOOL,
                arguments={
                    "query": "总结上传这篇 Meta 文档，总结文档要点",
                    "document_id": ingested.document_id,
                    "top_k": 5,
                },
            )
        )

    assert tool_result.status == "ok"
    assert tool_result.output["search"]["evidence_gate"]["decision"] == "supported"
    assert tool_result.output["results"]
    assert all(
        "document_summary" in row["match_signals"]
        for row in tool_result.output["results"]
    )
    assert any(
        "culture reset" in row["supported_passage"].lower()
        for row in tool_result.output["results"]
    )
