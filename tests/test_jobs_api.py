from fastapi.testclient import TestClient

from investment_agent.app import create_app
from investment_agent.cloud import JobStatus


class FakeQueue:
    def __init__(self):
        self.jobs = {}

    def enqueue(self, job):
        self.jobs[job.job_id] = {"status": "queued", "detail": ""}

    def get_status(self, job_id):
        return self.jobs.get(job_id)

    def set_status(self, job_id, status, detail=""):
        self.jobs[job_id] = {"status": status.value, "detail": detail}


def test_jobs_require_redis_configuration() -> None:
    client = TestClient(create_app())

    response = client.post("/jobs", json={"job_type": "healthcheck.v1"})

    assert response.status_code == 503


def test_job_submit_and_status_contract() -> None:
    app = create_app()
    queue = FakeQueue()
    app.state.job_queue = queue
    client = TestClient(app)

    submitted = client.post("/jobs", json={"job_type": "healthcheck.v1"})
    assert submitted.status_code == 202
    job_id = submitted.json()["job_id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"

    queue.set_status(job_id, JobStatus.COMPLETE, "ok")
    completed = client.get(f"/jobs/{job_id}").json()
    assert completed == {"job_id": job_id, "status": "complete", "detail": "ok"}
