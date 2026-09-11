from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from investment_agent.app import create_app
from investment_agent.cloud import LocalArtifactStore
from investment_agent.config import Settings
from investment_agent.repositories import (
    AgentRunCreate,
    AgentRunRepository,
    ClaimCreate,
    ModelCallCreate,
    ReportCreate,
    ReportRepository,
    ToolCallRecordCreate,
)
from investment_agent.storage import Base, EvidenceItem
from tests.helpers import write_minimal_text_pdf


def test_documents_api_ingests_and_lists_text_file(tmp_path) -> None:
    source = tmp_path / "acme.txt"
    source.write_text("ACME backlog improved after supplier capacity recovered.")
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    list_response = client.get("/documents")

    assert ingest_response.status_code == 201
    assert ingest_response.json()["created"]
    assert ingest_response.json()["evidence_count"] == 1
    assert ingest_response.json()["chunk_count"] == 1
    assert list_response.status_code == 200
    documents = list_response.json()
    assert len(documents) == 1
    assert documents[0]["title"] == "acme"
    assert documents[0]["source_type"] == "text"


def test_documents_api_ingests_pdf_file(tmp_path) -> None:
    source = tmp_path / "report.pdf"
    write_minimal_text_pdf(source, "PDF evidence supports the margin thesis.")
    client = client_for_tmp_db(tmp_path)

    response = client.post("/documents/ingest", json={"path": str(source)})
    documents = client.get("/documents").json()

    assert response.status_code == 201
    assert response.json()["evidence_count"] == 1
    assert response.json()["chunk_count"] == 1
    assert documents[0]["source_type"] == "pdf"
    assert documents[0]["metadata"]["page_count"] == 1


def test_documents_api_ingests_research_csv_file(tmp_path) -> None:
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
    client = client_for_tmp_db(tmp_path)

    response = client.post("/documents/ingest", json={"path": str(source)})
    documents = client.get("/documents").json()

    assert response.status_code == 201
    assert response.json()["evidence_count"] == 1
    assert response.json()["chunk_count"] == 1
    assert documents[0]["source_type"] == "csv"
    assert documents[0]["metadata"]["row_count"] == 2
    assert documents[0]["metadata"]["columns"] == [
        "year",
        "gold_return_pct",
        "real_yield_pct",
        "etf_flows_b",
    ]


def test_documents_api_uploads_browser_file_bytes(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/documents/upload",
        content=b"Gold demand remained firm as real yields eased.",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Argus-Filename": "gold_upload.md",
        },
    )
    documents = client.get("/documents").json()

    assert response.status_code == 201
    assert response.json()["created"]
    assert response.json()["evidence_count"] == 1
    assert response.json()["chunk_count"] == 1
    assert documents[0]["title"].endswith("gold_upload")
    assert documents[0]["source_type"] == "markdown"


def test_documents_api_decodes_unicode_browser_filename_and_deletes_source(
    tmp_path,
) -> None:
    client = client_for_tmp_db(tmp_path)

    upload = client.post(
        "/documents/upload",
        content="黄金价格可能受到实际利率影响。".encode(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Argus-Filename": "%E9%BB%84%E9%87%91%E7%A0%94%E7%A9%B6.md",
        },
    )
    document_id = upload.json()["document_id"]
    document = client.get("/documents").json()[0]
    upload_path = Path(unquote(urlparse(document["source_uri"]).path))
    artifact_path = (
        tmp_path / "artifacts" / "raw" / document["content_hash"] / "黄金研究.md"
    )

    assert upload.status_code == 201
    assert document["title"].endswith("黄金研究")
    assert upload_path.exists()
    assert artifact_path.exists()

    with client.app.state.session_factory() as session:
        run_repository = AgentRunRepository(session)
        related_run = run_repository.create_run(
            AgentRunCreate(
                run_key="document-delete-related",
                role="research",
                objective="Use the uploaded gold research",
                status="complete",
                sensitivity="internal",
                as_of_date=None,
                metadata={"document_id": document_id},
            )
        )
        run_repository.record_model_call(
            ModelCallCreate(
                run_id=related_run.id,
                provider="test-provider",
                model="test-model",
                deployment="cloud",
                prompt_tokens=5,
                completion_tokens=3,
                estimated_cost_usd=0.001,
            )
        )
        run_repository.record_tool_call(
            ToolCallRecordCreate(
                run_id=related_run.id,
                call_id="document-delete-call",
                tool_name="retrieve_evidence",
                status="success",
                arguments={"document_id": document_id},
                output={},
            )
        )
        unrelated_run = run_repository.create_run(
            AgentRunCreate(
                run_key="document-delete-unrelated",
                role="research",
                objective="Unrelated web research",
                status="complete",
                sensitivity="public",
                as_of_date=None,
                metadata={"document_id": None},
            )
        )
        related_report = ReportRepository(session).create_report(
            ReportCreate(
                title="Related report",
                report_type="research",
                status="complete",
                report_json={"run_id": related_run.id},
                rendered_html="<p>related</p>",
            )
        )
        evidence_id = session.scalar(
            select(EvidenceItem.id).where(EvidenceItem.document_id == document_id)
        )
        assert evidence_id is not None
        claim_related_run = run_repository.create_run(
            AgentRunCreate(
                run_key="document-delete-claim-related",
                role="research",
                objective="All-source research that cited this document",
                status="complete",
                sensitivity="internal",
                as_of_date=None,
                metadata={"document_id": None},
            )
        )
        run_repository.record_claim(
            ClaimCreate(
                run_id=claim_related_run.id,
                claim_text="The uploaded evidence supports this claim.",
                evidence_ids=[evidence_id],
                relations={},
            )
        )
        session.commit()
        related_run_id = related_run.id
        claim_related_run_id = claim_related_run.id
        unrelated_run_id = unrelated_run.id
        related_report_id = related_report.id

    assert client.delete(f"/documents/{document_id}").status_code == 204
    assert not upload_path.exists()
    assert not artifact_path.exists()
    assert client.get("/documents").json() == []
    assert client.get(f"/runs/{related_run_id}").status_code == 404
    assert client.get(f"/runs/{claim_related_run_id}").status_code == 404
    assert client.get(f"/reports/{related_report_id}").status_code == 404
    assert client.get(f"/runs/{unrelated_run_id}").status_code == 200
    dashboard = client.get("/runs").json()
    assert dashboard["model_call_count"] == 0
    assert dashboard["retained_run_usage"]["total_tokens"] == 0
    assert dashboard["historical_api_usage"]["call_count"] == 1
    assert dashboard["historical_api_usage"]["total_tokens"] == 8
    assert dashboard["tool_call_count"] == 0
    assert client.delete(f"/documents/{document_id}").status_code == 404


def test_documents_api_rejects_empty_browser_upload(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/documents/upload",
        content=b"",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Argus-Filename": "empty.md",
        },
    )

    assert response.status_code == 422


def test_documents_api_cleans_up_failed_scanned_pdf_upload(
    tmp_path,
    monkeypatch,
) -> None:
    client = client_for_tmp_db(tmp_path)
    scanned_pdf = tmp_path / "scan-source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(scanned_pdf)
    upload_root = tmp_path / "data" / "uploads"
    monkeypatch.chdir(tmp_path)

    response = client.post(
        "/documents/upload",
        content=scanned_pdf.read_bytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Argus-Filename": "scan.pdf",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "document_parse_failed"
    assert "no extractable text layer" in detail["message"]
    assert detail["external_calls"] == 0
    assert detail["partial_data_removed"] is True
    assert upload_root.exists()
    assert list(upload_root.iterdir()) == []


def test_documents_api_streams_and_stops_oversize_upload(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    client.app.state.settings = replace(
        client.app.state.settings,
        document_upload_max_bytes=8,
    )

    response = client.post(
        "/documents/upload",
        content=b"123456789",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Argus-Filename": "too-large.md",
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "upload_too_large"
    assert client.get("/documents").json() == []


def test_documents_api_reports_extracted_text_limit_and_cleans_up(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    client.app.state.settings = replace(
        client.app.state.settings,
        document_extracted_text_max_characters=10,
    )

    response = client.post(
        "/documents/upload",
        content=b"this source has more than ten characters",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Argus-Filename": "bounded.md",
        },
    )

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "extracted_text_limit_exceeded"
    assert detail["stage"] == "extract"
    assert detail["external_calls"] == 0
    assert client.get("/documents").json() == []


def test_documents_api_returns_existing_document_for_duplicate_content(
    tmp_path,
) -> None:
    source = tmp_path / "macro.md"
    source.write_text("# Macro\n\nGold demand remained firm.", encoding="utf-8")
    client = client_for_tmp_db(tmp_path)

    first = client.post("/documents/ingest", json={"path": str(source)})
    second = client.post("/documents/ingest", json={"path": str(source)})
    documents = client.get("/documents").json()

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["created"]
    assert not second.json()["created"]
    assert first.json()["document_id"] == second.json()["document_id"]
    assert len(documents) == 1


def test_documents_api_clears_all_indexed_uploads_and_orphans(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    for filename in ("macro.md", "rates.md"):
        response = client.post(
            "/documents/upload",
            content=f"Evidence from {filename}.".encode(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Argus-Filename": filename,
            },
        )
        assert response.status_code == 201

    upload_root = tmp_path / "data" / "uploads"
    orphan_dir = upload_root / "orphan"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "partial.tmp").write_text("partial", encoding="utf-8")

    response = client.delete("/documents")

    assert response.status_code == 200
    assert response.json() == {
        "documents_deleted": 2,
        "upload_files_deleted": 3,
        "runs_deleted": 0,
        "reports_deleted": 0,
    }
    assert client.get("/documents").json() == []
    assert upload_root.exists()
    assert list(upload_root.iterdir()) == []


def test_documents_api_maps_errors_to_http_statuses(tmp_path) -> None:
    workbook_file = tmp_path / "positions.xlsx"
    workbook_file.write_text("not a real workbook", encoding="utf-8")
    client = client_for_tmp_db(tmp_path)

    missing = client.post(
        "/documents/ingest",
        json={"path": str(tmp_path / "missing.txt")},
    )
    unsupported = client.post("/documents/ingest", json={"path": str(workbook_file)})

    assert missing.status_code == 404
    assert unsupported.status_code == 415


def client_for_tmp_db(tmp_path) -> TestClient:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        document_upload_root=str(tmp_path / "data" / "uploads"),
    )
    app = create_app(settings)
    app.state.artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)
