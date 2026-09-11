from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass(frozen=True)
class DocumentResourcePolicy:
    max_upload_bytes: int = 25 * MIB
    max_pdf_pages: int = 500
    max_extracted_characters: int = 2_000_000
    timeout_seconds: float = 90.0
    warning_rss_bytes: int = 1 * GIB
    max_rss_bytes: int = int(1.5 * GIB)
    poll_interval_seconds: float = 0.5
    terminate_grace_seconds: float = 5.0
    admission_memory_ratio: float = 0.70


class DocumentResourceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str,
        observed: int | float | None = None,
        limit: int | float | None = None,
        next_action: str,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.observed = observed
        self.limit = limit
        self.next_action = next_action
        self.status_code = status_code

    def to_detail(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "stage": self.stage,
            "observed": self.observed,
            "limit": self.limit,
            "next_action": self.next_action,
            "external_calls": 0,
            "partial_data_removed": True,
        }


@dataclass(frozen=True)
class ExtractionArtifact:
    directory: Path
    pages_path: Path
    page_count: int
    extracted_characters: int
    dataset_metadata: dict[str, object]
    peak_rss_bytes: int
    memory_warning: bool

    def cleanup(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)


def ensure_admission_capacity(policy: DocumentResourcePolicy) -> None:
    usage = cgroup_memory_usage()
    if usage is None:
        return
    current, maximum = usage
    if maximum <= 0:
        return
    ratio = current / maximum
    if ratio >= policy.admission_memory_ratio:
        raise DocumentResourceError(
            "system_memory_pressure",
            "Document parsing did not start because the Argus container is already under memory pressure.",
            stage="admission",
            observed=round(ratio, 4),
            limit=policy.admission_memory_ratio,
            next_action="Wait for another task to finish, then retry with a smaller document.",
            status_code=503,
        )


def extract_in_bounded_process(
    path: Path,
    source_type: str,
    policy: DocumentResourcePolicy,
    *,
    rss_reader: Callable[[int], int | None] | None = None,
) -> ExtractionArtifact:
    ensure_admission_capacity(policy)
    directory = Path(tempfile.mkdtemp(prefix="argus-extract-"))
    pages_path = directory / "pages.jsonl"
    status_path = directory / "status.json"
    command = [
        sys.executable,
        "-m",
        "investment_agent.ingestion.extract_worker",
        "--input",
        str(path),
        "--source-type",
        source_type,
        "--pages-output",
        str(pages_path),
        "--status-output",
        str(status_path),
        "--max-pages",
        str(policy.max_pdf_pages),
        "--max-characters",
        str(policy.max_extracted_characters),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    reader = rss_reader or process_rss_bytes
    started = time.monotonic()
    peak_rss = 0
    memory_warning = False
    effective_max_rss = _effective_child_limit(policy.max_rss_bytes)
    effective_warning_rss = min(
        policy.warning_rss_bytes,
        max(1, int(effective_max_rss * 0.75)),
    )
    try:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            rss = reader(process.pid) or 0
            peak_rss = max(peak_rss, rss)
            memory_warning = memory_warning or rss >= effective_warning_rss
            if rss > effective_max_rss:
                _stop_process(process, grace_seconds=policy.terminate_grace_seconds)
                raise DocumentResourceError(
                    "task_memory_limit_exceeded",
                    "Document parsing was stopped because the parser exceeded its memory limit.",
                    stage="extract",
                    observed=rss,
                    limit=effective_max_rss,
                    next_action="Split the PDF or upload a smaller text-based document, then retry.",
                )
            if elapsed > policy.timeout_seconds:
                _stop_process(process, grace_seconds=policy.terminate_grace_seconds)
                raise DocumentResourceError(
                    "task_timeout",
                    "Document parsing was stopped because it exceeded the allowed run time.",
                    stage="extract",
                    observed=round(elapsed, 3),
                    limit=policy.timeout_seconds,
                    next_action="Split the document into smaller files or remove image-heavy pages, then retry.",
                    status_code=504,
                )
            time.sleep(policy.poll_interval_seconds)

        if not status_path.is_file():
            raise DocumentResourceError(
                "parser_process_failed",
                f"The isolated parser exited unexpectedly with code {process.returncode}.",
                stage="extract",
                observed=process.returncode,
                next_action="Retry once; if it fails again, convert the source to searchable text or PDF.",
            )
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("status") != "ok":
            raise DocumentResourceError(
                str(status.get("code") or "document_parse_failed"),
                str(status.get("message") or "Document parsing failed."),
                stage=str(status.get("stage") or "extract"),
                observed=status.get("observed"),
                limit=status.get("limit"),
                next_action=str(
                    status.get("next_action")
                    or "Review the source file and retry with a smaller searchable document."
                ),
                status_code=int(status.get("status_code") or 422),
            )
        return ExtractionArtifact(
            directory=directory,
            pages_path=pages_path,
            page_count=int(status.get("page_count") or 0),
            extracted_characters=int(status.get("extracted_characters") or 0),
            dataset_metadata=dict(status.get("dataset_metadata") or {}),
            peak_rss_bytes=peak_rss,
            memory_warning=memory_warning,
        )
    except Exception:
        if process.poll() is None:
            _stop_process(process, grace_seconds=policy.terminate_grace_seconds)
        shutil.rmtree(directory, ignore_errors=True)
        raise


def process_rss_bytes(pid: int) -> int | None:
    status_path = Path(f"/proc/{pid}/status")
    if status_path.is_file():
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
        value = result.stdout.strip()
        return int(value) * 1024 if value else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def cgroup_memory_usage() -> tuple[int, int] | None:
    current_path = Path("/sys/fs/cgroup/memory.current")
    maximum_path = Path("/sys/fs/cgroup/memory.max")
    if not current_path.is_file() or not maximum_path.is_file():
        return None
    try:
        maximum_text = maximum_path.read_text(encoding="utf-8").strip()
        if maximum_text == "max":
            return None
        return (
            int(current_path.read_text(encoding="utf-8").strip()),
            int(maximum_text),
        )
    except (OSError, ValueError):
        return None


def _effective_child_limit(configured_limit: int) -> int:
    usage = cgroup_memory_usage()
    if usage is None:
        return configured_limit
    current, maximum = usage
    reserve = max(128 * MIB, int(maximum * 0.10))
    available = max(1, maximum - current - reserve)
    return min(configured_limit, available)


def _stop_process(process: subprocess.Popen[bytes], *, grace_seconds: float) -> None:
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=max(1.0, grace_seconds))
