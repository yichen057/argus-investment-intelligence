import pytest

from investment_agent.config import Settings
from investment_agent.ingestion import LocalFileIngestor, UnsupportedSourceType
from investment_agent.ingestion.chunking import chunk_text
from investment_agent.repositories import DocumentRepository
from investment_agent.storage import Base, make_engine, make_session_factory, session_scope
from tests.helpers import write_minimal_text_pdf


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


def test_chunk_text_is_deterministic_with_overlap() -> None:
    chunks = chunk_text("abcdefghijklmnopqrstuvwxyz", chunk_size=10, overlap=2)

    assert [chunk.text for chunk in chunks] == [
        "abcdefghij",
        "ijklmnopqr",
        "qrstuvwxyz",
    ]
    assert [(chunk.start_char, chunk.end_char) for chunk in chunks] == [
        (0, 10),
        (8, 18),
        (16, 26),
    ]


def test_local_text_ingestion_creates_document_evidence_and_chunks(tmp_path) -> None:
    source = tmp_path / "acme.txt"
    source.write_text(
        "ACME supply constraints eased in Q2. Margin improved.\n"
        "Management still warned about customer concentration.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = LocalFileIngestor(session, chunk_size=40, overlap=5).ingest_path(source)
        repository = DocumentRepository(session)
        document = repository.get_document(result.document_id)
        evidence = repository.list_evidence_for_document(result.document_id)
        chunks = repository.list_chunks_for_document(result.document_id)

    assert result.created
    assert result.evidence_count == 1
    assert result.chunk_count == 3
    assert document is not None
    assert document.source_type == "text"
    assert document.title == "acme"
    assert evidence[0].page_or_section == "full document"
    assert chunks[0].text.startswith("ACME supply constraints")


def test_local_markdown_ingestion_is_idempotent_by_content_hash(tmp_path) -> None:
    source = tmp_path / "macro.md"
    source.write_text(
        "# Gold Macro\n\nReal yields fell while central-bank demand stayed firm.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        ingestor = LocalFileIngestor(session, chunk_size=80, overlap=10)
        first = ingestor.ingest_path(source)
        second = ingestor.ingest_path(source)
        repository = DocumentRepository(session)
        documents = repository.list_documents()
        chunks = repository.list_chunks_for_document(first.document_id)

    assert first.created
    assert not second.created
    assert first.document_id == second.document_id
    assert first.content_hash == second.content_hash
    assert len(documents) == 1
    assert len(chunks) == 1


def test_local_pdf_ingestion_extracts_page_text(tmp_path) -> None:
    source = tmp_path / "research.pdf"
    write_minimal_text_pdf(
        source,
        "ACME PDF margin improved while supply normalized.",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = LocalFileIngestor(session, chunk_size=80, overlap=10).ingest_path(
            source
        )
        repository = DocumentRepository(session)
        document = repository.get_document(result.document_id)
        evidence = repository.list_evidence_for_document(result.document_id)
        chunks = repository.list_chunks_for_document(result.document_id)

    assert result.created
    assert result.evidence_count == 1
    assert result.chunk_count == 1
    assert document is not None
    assert document.source_type == "pdf"
    assert document.metadata_json["page_count"] == 1
    assert evidence[0].page_or_section == "page 1"
    assert evidence[0].metadata_json["page_number"] == 1
    assert "ACME PDF margin improved" in chunks[0].text
    assert chunks[0].metadata_json["page_number"] == 1


def test_local_csv_ingestion_creates_dataset_metadata(tmp_path) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct,etf_flows_b",
                "2023,13,1.8,-1",
                "2024,27,1.5,2",
            ]
        ),
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = LocalFileIngestor(session, chunk_size=200, overlap=20).ingest_path(
            source
        )
        repository = DocumentRepository(session)
        document = repository.get_document(result.document_id)
        evidence = repository.list_evidence_for_document(result.document_id)
        chunks = repository.list_chunks_for_document(result.document_id)

    assert result.created
    assert result.evidence_count == 1
    assert result.chunk_count == 1
    assert document is not None
    assert document.source_type == "csv"
    assert document.metadata_json["row_count"] == 2
    assert document.metadata_json["columns"] == [
        "year",
        "gold_return_pct",
        "real_yield_pct",
        "etf_flows_b",
    ]
    assert evidence[0].page_or_section == "dataset rows"
    assert "gold_return_pct" in evidence[0].excerpt
    assert chunks[0].text.startswith("year,gold_return_pct")


def test_local_ingestion_rejects_unsupported_file_type(tmp_path) -> None:
    source = tmp_path / "data.xlsx"
    source.write_text("not a real workbook", encoding="utf-8")
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        with pytest.raises(UnsupportedSourceType):
            LocalFileIngestor(session).ingest_path(source)
