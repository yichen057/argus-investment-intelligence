import pytest
from datetime import date

from investment_agent.config import Settings
from investment_agent.embeddings import DeterministicHashEmbeddingProvider, EmbeddingService
from investment_agent.ingestion import LocalFileIngestor
from investment_agent.repositories import (
    ChunkCreate,
    DocumentCreate,
    DocumentRepository,
    EvidenceItemCreate,
)
from investment_agent.retrieval import VectorRetrievalService
from investment_agent.storage import Base, make_engine, make_session_factory, session_scope


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


def session_factory_for_tmp_db(tmp_path):
    settings = sqlite_settings(f"sqlite:///{tmp_path / 'argus.db'}")
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_vector_retrieval_returns_ranked_evidence_snippets(tmp_path) -> None:
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

    with session_scope(session_factory) as session:
        gold_result = LocalFileIngestor(session).ingest_path(gold)
        supply_result = LocalFileIngestor(session).ingest_path(supply)
        embedding_service = EmbeddingService(session, provider)
        embedding_service.embed_document_chunks(gold_result.document_id)
        embedding_service.embed_document_chunks(supply_result.document_id)

        results = VectorRetrievalService(session, provider).retrieve(
            "gold real yields central banks",
            top_k=2,
        )

    assert len(results) == 2
    assert results[0].title == "gold"
    assert "Gold demand strengthened" in results[0].text
    assert results[0].evidence_item_id is not None
    assert results[0].page_or_section == "full document"
    assert results[0].evidence_grade == "source"
    assert results[0].score >= results[1].score


def test_vector_retrieval_applies_access_scope_filter(tmp_path) -> None:
    source = tmp_path / "restricted.md"
    source.write_text("Restricted household portfolio notes mention liquidity needs.")
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_scope(session_factory) as session:
        result = LocalFileIngestor(session).ingest_path(source)
        EmbeddingService(session, provider).embed_document_chunks(result.document_id)
        no_results = VectorRetrievalService(session, provider).retrieve(
            "portfolio liquidity",
            top_k=3,
            access_scope="public",
        )
        internal_results = VectorRetrievalService(session, provider).retrieve(
            "portfolio liquidity",
            top_k=3,
            access_scope="internal",
        )

    assert no_results == []
    assert len(internal_results) == 1
    assert internal_results[0].title == "restricted"


def test_vector_retrieval_excludes_future_dated_evidence(tmp_path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_scope(session_factory) as session:
        repository = DocumentRepository(session)
        old_document = repository.create_document(
            DocumentCreate(
                source_uri="file:///old-gold.md",
                source_type="markdown",
                title="old-gold",
                content_hash="sha256:old-document",
            )
        )
        old_evidence = repository.create_evidence_item(
            EvidenceItemCreate(
                document_id=old_document.id,
                source_uri=old_document.source_uri,
                source_type=old_document.source_type,
                title=old_document.title,
                evidence_grade="source",
                excerpt="Gold demand rose as real yields fell in 2024.",
                content_hash="sha256:old-evidence",
                publication_date=date(2024, 6, 30),
                data_as_of_date=date(2024, 6, 30),
            )
        )
        repository.create_chunk(
            ChunkCreate(
                document_id=old_document.id,
                evidence_item_id=old_evidence.id,
                chunk_index=0,
                text="Gold demand rose as real yields fell in 2024.",
                content_hash="sha256:old-chunk",
            )
        )

        future_document = repository.create_document(
            DocumentCreate(
                source_uri="file:///future-gold.md",
                source_type="markdown",
                title="future-gold",
                content_hash="sha256:future-document",
            )
        )
        future_evidence = repository.create_evidence_item(
            EvidenceItemCreate(
                document_id=future_document.id,
                source_uri=future_document.source_uri,
                source_type=future_document.source_type,
                title=future_document.title,
                evidence_grade="source",
                excerpt="Gold demand rose as real yields fell in 2027.",
                content_hash="sha256:future-evidence",
                publication_date=date(2027, 1, 1),
                data_as_of_date=date(2027, 1, 1),
            )
        )
        repository.create_chunk(
            ChunkCreate(
                document_id=future_document.id,
                evidence_item_id=future_evidence.id,
                chunk_index=0,
                text="Gold demand rose as real yields fell in 2027.",
                content_hash="sha256:future-chunk",
            )
        )
        EmbeddingService(session, provider).embed_document_chunks(old_document.id)
        EmbeddingService(session, provider).embed_document_chunks(future_document.id)

        historical_results = VectorRetrievalService(session, provider).retrieve(
            "gold real yields demand",
            top_k=5,
            as_of_date=date(2025, 1, 1),
        )
        hindsight_results = VectorRetrievalService(session, provider).retrieve(
            "gold real yields demand",
            top_k=5,
            as_of_date=date(2028, 1, 1),
        )

    assert {result.title for result in historical_results} == {"old-gold"}
    assert {result.title for result in hindsight_results} == {
        "old-gold",
        "future-gold",
    }


def test_vector_retrieval_rejects_invalid_top_k(tmp_path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_scope(session_factory) as session:
        service = VectorRetrievalService(session, provider)
        with pytest.raises(ValueError) as exc_info:
            service.retrieve("query", top_k=0)

    assert str(exc_info.value) == "top_k must be positive"
