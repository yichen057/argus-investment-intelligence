from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.evaluation import EvalRunner

router = APIRouter(prefix="/eval", tags=["evaluation"])


class EvalRunRequest(BaseModel):
    dataset_path: str = Field(default="evals/golden_questions.yaml", min_length=1)
    save_artifacts: bool = True
    output_dir: str = Field(default="eval-results", min_length=1)


class EvalRunResponse(BaseModel):
    dataset_version: int
    dataset_path: str
    started_at: str
    completed_at: str
    cases_total: int
    cases_passed: int
    cases_failed: int
    cases_partial: int
    cases_skipped: int
    total_tokens: int
    total_estimated_cost_usd: float
    avg_latency_ms: float | None
    metrics: dict[str, Any]
    artifact_paths: dict[str, str]
    case_results: list[dict[str, Any]]


@router.post("/run", response_model=EvalRunResponse)
def run_eval(
    request: EvalRunRequest,
    session: Session = Depends(get_db_session),
) -> EvalRunResponse:
    try:
        result = EvalRunner(session).run(
            dataset_path=Path(request.dataset_path),
            save_artifacts=request.save_artifacts,
            output_dir=Path(request.output_dir),
        )
    except FileNotFoundError as exc:
        missing_path = exc.filename or "an evaluation input"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Local test input is missing: {missing_path}. "
                "Recreate the backend container so the evals and examples mounts are applied."
            ),
        ) from exc
    payload = result.to_dict()
    return EvalRunResponse(**payload)
