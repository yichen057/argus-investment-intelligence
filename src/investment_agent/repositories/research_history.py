from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from investment_agent.storage.models import (
    AgentRun,
    Chunk,
    Claim,
    EvidenceItem,
    EvidenceLedgerLink,
    EvidenceLedgerQuery,
    ModelCall,
    Report,
    ToolCallRecord,
)


@dataclass(frozen=True)
class ResearchHistoryPurge:
    run_ids: tuple[int, ...]
    report_ids: tuple[int, ...]


class ResearchHistoryRepository:
    """Delete research history that snapshots a removed input.

    Run-to-input references intentionally live in immutable JSON snapshots and the
    Evidence Ledger rather than mutable foreign keys. Deletion therefore resolves
    those references before removing the source or method document.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def purge_for_document(self, document_id: int) -> ResearchHistoryPurge:
        evidence_ids = set(
            self._session.scalars(
                select(EvidenceItem.id).where(EvidenceItem.document_id == document_id)
            )
        )
        chunk_ids = set(
            self._session.scalars(
                select(Chunk.id).where(Chunk.document_id == document_id)
            )
        )
        run_ids = {
            run.id
            for run in self._session.scalars(select(AgentRun))
            if _json_has_integer(run.metadata_json, "document_id", document_id)
        }
        run_ids.update(
            link.run_id
            for link in self._session.scalars(select(EvidenceLedgerLink))
            if link.chunk_id in chunk_ids or link.evidence_item_id in evidence_ids
        )
        run_ids.update(
            claim.run_id
            for claim in self._session.scalars(select(Claim))
            if claim.run_id is not None
            and any(item in evidence_ids for item in claim.evidence_ids_json)
        )
        run_ids.update(
            call.run_id
            for call in self._session.scalars(select(ToolCallRecord))
            if _json_has_integer(call.arguments_json, "document_id", document_id)
            or _json_has_integer(call.output_json, "document_id", document_id)
        )
        direct_reports = [
            report
            for report in self._session.scalars(select(Report))
            if _json_has_any_evidence_id(report.report_json, evidence_ids)
        ]
        direct_report_ids = {report.id for report in direct_reports}
        run_ids.update(
            run_id
            for report in direct_reports
            if (run_id := _top_level_integer(report.report_json, "run_id")) is not None
        )
        return self._purge(run_ids, direct_report_ids=direct_report_ids)

    def purge_for_method_document(
        self,
        document_id: int,
        *,
        content_hash: str,
    ) -> ResearchHistoryPurge:
        run_ids = {
            run.id
            for run in self._session.scalars(select(AgentRun))
            if _metadata_uses_method_document(
                run.metadata_json,
                document_id=document_id,
                content_hash=content_hash,
            )
        }
        return self._purge(run_ids)

    def _purge(
        self,
        run_ids: set[int],
        *,
        direct_report_ids: set[int] | None = None,
    ) -> ResearchHistoryPurge:
        report_ids = set(direct_report_ids or ())
        if run_ids:
            report_ids.update(
                report.id
                for report in self._session.scalars(select(Report))
                if _json_has_integer(report.report_json, "run_id", run_ids)
            )

        claim_filters = []
        if report_ids:
            claim_filters.append(Claim.report_id.in_(report_ids))
        if run_ids:
            claim_filters.append(Claim.run_id.in_(run_ids))
        for condition in claim_filters:
            self._session.execute(delete(Claim).where(condition))

        if report_ids:
            self._session.execute(delete(Report).where(Report.id.in_(report_ids)))
        if run_ids:
            self._session.execute(
                delete(EvidenceLedgerLink).where(EvidenceLedgerLink.run_id.in_(run_ids))
            )
            self._session.execute(
                delete(EvidenceLedgerQuery).where(
                    EvidenceLedgerQuery.run_id.in_(run_ids)
                )
            )
            self._session.execute(
                delete(ModelCall).where(ModelCall.run_id.in_(run_ids))
            )
            self._session.execute(
                delete(ToolCallRecord).where(ToolCallRecord.run_id.in_(run_ids))
            )
            self._session.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))
        self._session.flush()
        return ResearchHistoryPurge(
            run_ids=tuple(sorted(run_ids)),
            report_ids=tuple(sorted(report_ids)),
        )


def _metadata_uses_method_document(
    metadata: dict[str, Any],
    *,
    document_id: int,
    content_hash: str,
) -> bool:
    snapshot = metadata.get("method_document")
    if not isinstance(snapshot, dict):
        return False
    return (
        _is_integer(snapshot.get("id"), document_id)
        or snapshot.get("content_hash") == content_hash
    )


def _json_has_integer(
    value: Any,
    key: str,
    expected: int | set[int],
) -> bool:
    expected_values = expected if isinstance(expected, set) else {expected}
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key and any(
                _is_integer(current_value, item) for item in expected_values
            ):
                return True
            if _json_has_integer(current_value, key, expected_values):
                return True
    elif isinstance(value, list):
        return any(_json_has_integer(item, key, expected_values) for item in value)
    return False


def _json_has_any_evidence_id(value: Any, evidence_ids: set[int]) -> bool:
    if not evidence_ids:
        return False
    if isinstance(value, dict):
        for key, current_value in value.items():
            if key == "evidence_id" and any(
                _is_integer(current_value, item) for item in evidence_ids
            ):
                return True
            if (
                key == "evidence_ids"
                and isinstance(current_value, list)
                and any(
                    any(_is_integer(item, expected) for expected in evidence_ids)
                    for item in current_value
                )
            ):
                return True
            if _json_has_any_evidence_id(current_value, evidence_ids):
                return True
    elif isinstance(value, list):
        return any(_json_has_any_evidence_id(item, evidence_ids) for item in value)
    return False


def _is_integer(value: Any, expected: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value == expected


def _top_level_integer(value: dict[str, Any], key: str) -> int | None:
    candidate = value.get(key)
    return (
        candidate
        if not isinstance(candidate, bool) and isinstance(candidate, int)
        else None
    )
