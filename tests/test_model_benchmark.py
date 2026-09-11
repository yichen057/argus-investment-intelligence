from __future__ import annotations

from pathlib import Path

from investment_agent.config import Settings
from investment_agent.evaluation.model_benchmark import ModelBenchmarkRunner
from investment_agent.providers.types import Deployment, ModelRequest, ModelResponse


class FakeBenchmarkProvider:
    deployment = Deployment.CLOUD
    serving_engine = "fake-api"

    def __init__(self, model_name: str, *, cost: float) -> None:
        self.provider_name = "fake"
        self.model_name = model_name
        self._cost = cost
        self.calls = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if "Evidence extraction benchmark" in request.objective:
            content = "- Revenue grew 12% in 2025 [source:W1]."
        else:
            content = (
                "## Direct answer\nRevenue grew 12% in 2025 [source:W1].\n"
                "## Supporting evidence\nRevenue grew 12% in 2025 [source:W1]."
            )
        return ModelResponse(
            provider=self.provider_name,
            model=self.model_name,
            deployment=self.deployment,
            serving_engine=self.serving_engine,
            content=content,
            prompt_tokens=100,
            completion_tokens=30,
            estimated_cost_usd=self._cost,
        )


def test_model_benchmark_scores_stages_and_prefers_near_top_lower_cost(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "benchmark.yaml"
    dataset.write_text(
        """version: 1
cases:
  - id: revenue
    question: Did revenue grow?
    evidence:
      - citation_id: W1
        title: Results
        text: Revenue grew 12% in 2025.
    expected_claim_terms:
      - [revenue, 12%, 2025]
    required_headings: [Direct answer, Supporting evidence]
""",
        encoding="utf-8",
    )
    settings = _settings(tmp_path)
    result = ModelBenchmarkRunner(
        settings,
        providers={
            "fake/cheap": FakeBenchmarkProvider("cheap", cost=0.001),
            "fake/costly": FakeBenchmarkProvider("costly", cost=0.005),
        },
    ).run(
        dataset_path=dataset,
        model_ids=("fake/cheap", "fake/costly"),
        max_cost_usd=0.05,
    )

    assert len(result.scores) == 4
    assert all(score.supported_claim_rate == 1.0 for score in result.scores)
    assert result.stage_recommendations["evidence_extraction"]["model_id"] == (
        "fake/cheap"
    )
    assert result.stage_recommendations["answer_synthesis"]["model_id"] == (
        "fake/cheap"
    )
    assert result.total_estimated_cost_usd == 0.012


def test_model_benchmark_never_calls_unconfigured_models(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = ModelBenchmarkRunner(settings).run(
        dataset_path=Path("evals/model_stage_benchmark.yaml"),
        model_ids=(f"openai/{settings.openai_model}",),
        max_cost_usd=0.01,
    )

    assert result.scores == ()
    assert result.skipped_models[f"openai/{settings.openai_model}"] == (
        "API key is not configured."
    )


def test_model_benchmark_reserves_worst_case_cost_before_provider_call(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    model_id = f"deepseek/{settings.deepseek_model}"
    provider = FakeBenchmarkProvider(settings.deepseek_model, cost=0.0)

    result = ModelBenchmarkRunner(
        settings,
        providers={model_id: provider},
    ).run(
        dataset_path=Path("evals/model_stage_benchmark.yaml"),
        model_ids=(model_id,),
        max_cost_usd=0.00001,
    )

    assert provider.calls == 0
    assert result.scores == ()
    assert "conservative maximum" in result.skipped_models[model_id]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'benchmark.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="manual",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )
