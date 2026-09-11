from __future__ import annotations

from pathlib import Path

import yaml

from investment_agent.config import Settings
from investment_agent.evaluation import EvalRunner
from investment_agent.storage import (
    Base,
    make_engine,
    make_session_factory,
    session_scope,
)


def test_eval_runner_measures_research_portfolio_and_saves_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought "
        "more reserves.",
        encoding="utf-8",
    )
    holdings = tmp_path / "holdings.csv"
    holdings.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                "AAA,AAA Corp,Equity,10,100,1000,900,Taxable",
                "BBB,BBB Bond,Bond,10,50,500,450,IRA",
            ]
        ),
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
  - id: no_evidence_001
    category: no_evidence
    question: "What does the source say about semiconductor wafer starts?"
    fixture: "{source.as_posix()}"
    checks: [no_unsupported_claims]
  - id: portfolio_001
    category: deterministic_portfolio
    fixture: "{holdings.as_posix()}"
    expected:
      total_value: 1500
      largest_weight: 0.6666666666666666
    checks: [exact_total_value, exact_concentration, scenario_generated]
""",
        encoding="utf-8",
    )
    session_factory = _session_factory(tmp_path)

    with session_scope(session_factory) as session:
        result = EvalRunner(session, project_root=tmp_path).run(
            dataset_path=dataset,
            output_dir=tmp_path / "eval-results",
        )

    assert result.cases_total == 3
    assert result.cases_failed == 0
    assert result.total_tokens > 0
    assert result.metrics["citation_coverage_rate"] == 1.0
    assert Path(result.artifact_paths["json"]).exists()
    assert Path(result.artifact_paths["markdown"]).exists()


def test_repository_golden_dataset_references_runtime_fixtures() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dataset_path = project_root / "evals" / "golden_questions.yaml"
    dataset = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))

    missing = [
        case["fixture"]
        for case in dataset["cases"]
        if case.get("fixture") and not (project_root / case["fixture"]).is_file()
    ]

    assert missing == []


def _session_factory(tmp_path: Path):
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'eval_runner.db'}",
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
