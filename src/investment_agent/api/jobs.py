from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from investment_agent.cloud import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    job_type: str = Field(pattern=r"^(document\.ingest\.v1|healthcheck\.v1)$")
    payload: dict = Field(default_factory=dict)


class JobResponse(BaseModel):
    job_id: str
    status: str
    detail: str = ""


def _queue(request: Request):
    queue = request.app.state.job_queue
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background jobs require ARGUS_REDIS_URL.",
        )
    return queue


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(body: JobCreateRequest, request: Request) -> JobResponse:
    if body.job_type == "document.ingest.v1" and not body.payload.get("path"):
        raise HTTPException(status_code=422, detail="document.ingest.v1 requires path")
    job = Job(job_type=body.job_type, payload=body.payload)
    _queue(request).enqueue(job)
    return JobResponse(job_id=job.job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, request: Request) -> JobResponse:
    value = _queue(request).get_status(job_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        job_id=job_id,
        status=value.get("status", "unknown"),
        detail=value.get("detail", ""),
    )
