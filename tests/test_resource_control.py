from __future__ import annotations

from pathlib import Path

import pytest

from investment_agent.ingestion.resources import (
    DocumentResourceError,
    DocumentResourcePolicy,
    extract_in_bounded_process,
)


def test_isolated_parser_is_killed_with_memory_reason(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_text("evidence " * 100_000, encoding="utf-8")
    policy = DocumentResourcePolicy(
        max_upload_bytes=2_000_000,
        max_extracted_characters=2_000_000,
        warning_rss_bytes=5,
        max_rss_bytes=10,
        poll_interval_seconds=0.001,
        terminate_grace_seconds=0.1,
        admission_memory_ratio=1.1,
    )

    with pytest.raises(DocumentResourceError) as raised:
        extract_in_bounded_process(
            source,
            "text",
            policy,
            rss_reader=lambda _pid: 11,
        )

    assert raised.value.code == "task_memory_limit_exceeded"
    assert raised.value.to_detail()["external_calls"] == 0
    assert raised.value.to_detail()["partial_data_removed"] is True


def test_isolated_parser_is_killed_with_timeout_reason(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_text("evidence " * 100_000, encoding="utf-8")
    policy = DocumentResourcePolicy(
        max_upload_bytes=2_000_000,
        max_extracted_characters=2_000_000,
        timeout_seconds=0.0001,
        warning_rss_bytes=10**12,
        max_rss_bytes=10**12,
        poll_interval_seconds=0.001,
        terminate_grace_seconds=0.1,
        admission_memory_ratio=1.1,
    )

    with pytest.raises(DocumentResourceError) as raised:
        extract_in_bounded_process(
            source,
            "text",
            policy,
            rss_reader=lambda _pid: 0,
        )

    assert raised.value.code == "task_timeout"
    assert raised.value.status_code == 504
