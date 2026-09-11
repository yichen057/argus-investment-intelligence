from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from investment_agent.app import create_app
from investment_agent.config import Settings
from investment_agent.storage import Base


def test_run_eval_api_returns_metrics(tmp_path: Path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought "
        "more reserves.",
        encoding="utf-8",
    )
    dataset = tmp_path / "golden.yaml"
    dataset.write_text(
        f"""
version: 1
cases:
  - id: gold_001
    category: direct_retrieval
    question: "Why might gold benefit when real yields fall?"
    fixture: "{source.as_posix()}"
    checks: [cited_material_claims]
""",
        encoding="utf-8",
    )
    client = _client_for_tmp_db(tmp_path)

    response = client.post(
        "/eval/run",
        json={"dataset_path": str(dataset), "save_artifacts": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cases_total"] == 1
    assert payload["cases_passed"] == 1
    assert payload["metrics"]["citation_coverage_rate"] == 1.0
    assert payload["artifact_paths"] == {}


def test_run_eval_api_explains_missing_local_input(tmp_path: Path) -> None:
    client = _client_for_tmp_db(tmp_path)

    response = client.post(
        "/eval/run",
        json={
            "dataset_path": str(tmp_path / "missing-golden.yaml"),
            "save_artifacts": False,
        },
    )

    assert response.status_code == 503
    assert "Local test input is missing" in response.json()["detail"]


def _client_for_tmp_db(tmp_path: Path) -> TestClient:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'eval_api.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)
