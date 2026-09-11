from __future__ import annotations

import logging
import signal
from pathlib import Path

from investment_agent.cloud import Job, JobStatus, RedisJobQueue
from investment_agent.config import get_settings
from investment_agent.embeddings import DeterministicHashEmbeddingProvider, EmbeddingService
from investment_agent.ingestion import LocalFileIngestor
from investment_agent.storage import make_engine, make_session_factory, session_scope

logger = logging.getLogger(__name__)


def _process(job: Job, session_factory) -> str:
    if job.job_type == "document.ingest.v1":
        path = Path(str(job.payload["path"]))
        with session_scope(session_factory) as session:
            result = LocalFileIngestor(session).ingest_path(path)
            EmbeddingService(
                session,
                DeterministicHashEmbeddingProvider(dimensions=16),
            ).embed_document_chunks(result.document_id)
        return f"document_id={result.document_id}"
    if job.job_type == "healthcheck.v1":
        return "ok"
    raise ValueError(f"Unsupported job type: {job.job_type}")


def main() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("ARGUS_REDIS_URL is required for the worker")
    queue = RedisJobQueue(settings.redis_url)
    session_factory = make_session_factory(make_engine(settings))
    stopping = False

    def stop(*_args) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("Argus worker started")
    while not stopping:
        job = queue.dequeue(timeout_seconds=5)
        if job is None:
            continue
        queue.set_status(job.job_id, JobStatus.RUNNING)
        try:
            detail = _process(job, session_factory)
        except Exception as exc:
            logger.exception("Job %s failed", job.job_id)
            queue.set_status(job.job_id, JobStatus.FAILED, str(exc))
        else:
            queue.set_status(job.job_id, JobStatus.COMPLETE, detail)


if __name__ == "__main__":
    main()
