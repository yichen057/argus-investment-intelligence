import pytest
from types import SimpleNamespace

from investment_agent.config import Settings
from investment_agent.embeddings import (
    DeterministicHashEmbeddingProvider,
    EmbeddingQuotaExceededError,
    EmbeddingService,
    GeminiEmbeddingProvider,
    RETRIEVAL_QUERY,
)
from investment_agent.ingestion import LocalFileIngestor
from investment_agent.repositories import DocumentRepository
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


def test_deterministic_hash_embedding_is_stable_and_normalized() -> None:
    provider = DeterministicHashEmbeddingProvider(dimensions=8)

    first = provider.embed("gold demand gold")
    second = provider.embed("gold demand gold")

    assert first.values == second.values
    assert first.dimensions == 8
    assert first.provider == "local"
    assert first.model == "deterministic-hash-v1"
    assert sum(value * value for value in first.values) == pytest.approx(1.0)


def test_embedding_service_indexes_document_chunks_once(tmp_path) -> None:
    source = tmp_path / "research.md"
    source.write_text(
        "# Research\n\nSupply normalized and margins improved for ACME.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        ingestion_result = LocalFileIngestor(
            session, chunk_size=40, overlap=5
        ).ingest_path(source)
        provider = DeterministicHashEmbeddingProvider(dimensions=12)
        service = EmbeddingService(session, provider)
        first = service.embed_document_chunks(ingestion_result.document_id)
        second = service.embed_document_chunks(ingestion_result.document_id)
        embeddings = DocumentRepository(session).list_embeddings_for_document(
            ingestion_result.document_id
        )

    assert ingestion_result.chunk_count == 2
    assert first.embedded_count == 2
    assert second.embedded_count == 0
    assert len(embeddings) == 2
    assert embeddings[0].provider == "local"
    assert embeddings[0].model == "deterministic-hash-v1"
    assert embeddings[0].dimensions == 12
    assert len(embeddings[0].embedding_json) == 12


class FakeEmbeddingModels:
    def __init__(self, *, values=None, error: Exception | None = None) -> None:
        self.values = values
        self.error = error
        self.calls: list[dict] = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=self.values)]
        )


class FakeEmbeddingClient:
    def __init__(self, models: FakeEmbeddingModels) -> None:
        self.models = models


def test_gemini_embedding_provider_creates_normalized_semantic_vector() -> None:
    models = FakeEmbeddingModels(values=[3.0, 4.0])
    provider = GeminiEmbeddingProvider(
        api_key="",
        dimensions=2,
        client=FakeEmbeddingClient(models),
    )

    vector = provider.embed("drivers of gold prices", task_type=RETRIEVAL_QUERY)

    assert vector.provider == "google"
    assert vector.model == "gemini-embedding-001"
    assert vector.values == pytest.approx((0.6, 0.8))
    assert models.calls[0]["config"] == {
        "task_type": "RETRIEVAL_QUERY",
        "output_dimensionality": 2,
    }


def test_gemini_embedding_provider_maps_429_without_paid_fallback() -> None:
    models = FakeEmbeddingModels(error=RuntimeError("429 RESOURCE_EXHAUSTED"))
    provider = GeminiEmbeddingProvider(
        api_key="",
        dimensions=2,
        client=FakeEmbeddingClient(models),
    )

    with pytest.raises(EmbeddingQuotaExceededError, match="will not upgrade"):
        provider.embed("gold")
