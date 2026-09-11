from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from investment_agent.config import get_settings
from investment_agent.evaluation import EvalRunner
from investment_agent.storage import Base, make_engine, make_session_factory, session_scope


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Argus local evals.")
    parser.add_argument(
        "--dataset",
        default="evals/golden_questions.yaml",
        help="Path to the eval dataset YAML file.",
    )
    parser.add_argument(
        "--output-dir",
        default="eval-results",
        help="Directory for generated JSON and Markdown eval reports.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print the report without saving artifacts.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    with session_scope(session_factory) as session:
        result = EvalRunner(session).run(
            dataset_path=Path(args.dataset),
            save_artifacts=not args.no_save,
            output_dir=Path(args.output_dir),
        )
    print(result.to_markdown())


if __name__ == "__main__":
    main()
