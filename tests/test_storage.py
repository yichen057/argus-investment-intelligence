import pytest

pytest.importorskip("sqlalchemy")

from investment_agent.config import Settings
from investment_agent.repositories import (
    DocumentCreate,
    DocumentRepository,
    EvidenceItemCreate,
)
from investment_agent.storage import (
    Base,
    make_engine,
    make_session_factory,
    session_scope,
)


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


def test_v1_metadata_contains_required_tables() -> None:
    required_tables = {
        "documents",
        "evidence_items",
        "chunks",
        "chunk_embeddings",
        "reports",
        "claims",
        "portfolio_positions",
        "user_profiles",
        "agent_runs",
        "tool_calls",
        "model_calls",
        "api_usage_ledger",
        "provider_billing_snapshots",
    }

    assert required_tables <= set(Base.metadata.tables)


def test_document_repository_write_read_round_trip(tmp_path) -> None:
    settings = sqlite_settings(f"sqlite:///{tmp_path / 'argus.db'}")
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)

    with session_scope(session_factory) as session:
        repository = DocumentRepository(session)
        document = repository.create_document(
            DocumentCreate(
                source_uri="file:///research/acme.md",
                source_type="markdown",
                title="ACME Research",
                content_hash="sha256:document",
                metadata={"sector": "industrials"},
            )
        )
        repository.create_evidence_item(
            EvidenceItemCreate(
                document_id=document.id,
                source_uri=document.source_uri,
                source_type=document.source_type,
                title=document.title,
                evidence_grade="source",
                excerpt="ACME margin expanded because supply normalized.",
                content_hash="sha256:evidence",
            )
        )
        document_id = document.id

    with session_scope(session_factory) as session:
        repository = DocumentRepository(session)
        stored = repository.get_document_by_hash("sha256:document")
        evidence = repository.list_evidence_for_document(document_id)

    assert stored is not None
    assert stored.title == "ACME Research"
    assert stored.metadata_json == {"sector": "industrials"}
    assert len(evidence) == 1
    assert evidence[0].excerpt == "ACME margin expanded because supply normalized."
