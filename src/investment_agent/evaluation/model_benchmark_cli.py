from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from investment_agent.config import get_settings
from investment_agent.evaluation.model_benchmark import (
    ModelBenchmarkRunner,
    save_model_benchmark,
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run an explicit, cost-capped Argus model-stage benchmark."
    )
    parser.add_argument(
        "--dataset",
        default="evals/model_stage_benchmark.yaml",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Explicit model IDs; Argus never adds a hidden fallback.",
    )
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--output-dir", default="eval-results")
    args = parser.parse_args(argv)
    result = ModelBenchmarkRunner(get_settings()).run(
        dataset_path=Path(args.dataset),
        model_ids=tuple(args.models),
        max_cost_usd=args.max_cost_usd,
    )
    paths = save_model_benchmark(result, output_dir=Path(args.output_dir))
    print(result.to_markdown())
    print(f"Artifacts: {paths}")


if __name__ == "__main__":
    main()
