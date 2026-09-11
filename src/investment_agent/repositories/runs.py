from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from investment_agent.storage.models import (
    AgentRun,
    ApiUsageLedger,
    Chunk,
    Claim,
    EvidenceLedgerLink,
    EvidenceLedgerQuery,
    ModelCall,
    ProviderAccountSnapshot,
    ProviderBillingSnapshot,
    ToolCallRecord,
)


@dataclass(frozen=True)
class AgentRunCreate:
    run_key: str
    role: str
    objective: str
    status: str
    sensitivity: str
    as_of_date: date | None
    selection_mode: str = "auto"
    selected_model: str | None = None
    selection_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallRecordCreate:
    run_id: int
    call_id: str
    tool_name: str
    status: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    error_code: str | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class ModelCallCreate:
    run_id: int
    provider: str
    model: str
    deployment: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    serving_engine: str | None = None
    latency_ms: int | None = None
    success: bool = True
    input_cost_per_million_usd: float | None = None
    output_cost_per_million_usd: float | None = None
    request_count: int = 1


@dataclass(frozen=True)
class ClaimCreate:
    run_id: int
    claim_text: str
    evidence_ids: list[int]
    relations: dict[str, str]
    confidence: float | None = None
    report_id: int | None = None


@dataclass(frozen=True)
class ModelCallAggregate:
    provider: str
    model: str
    deployment: str
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_estimated_cost_usd: float
    avg_latency_ms: float | None


@dataclass(frozen=True)
class ApiUsageAggregate:
    provider: str
    model: str
    deployment: str
    input_cost_per_million_usd: float | None
    output_cost_per_million_usd: float | None
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_estimated_cost_usd: float


@dataclass(frozen=True)
class UsageTotals:
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_estimated_cost_usd: float
    first_recorded_at: datetime | None
    last_recorded_at: datetime | None


@dataclass(frozen=True)
class ProviderBillingSnapshotCreate:
    provider: str
    period_start: date
    period_end: date
    currency: str
    actual_cost: Decimal | float
    total_tokens: int | None = None
    request_count: int | None = None
    source_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_key: str | None = None


@dataclass(frozen=True)
class ProviderAccountSnapshotCreate:
    provider: str
    billing_status: str
    billing_tier: str | None = None
    currency: str | None = None
    available_balance: Decimal | float | None = None
    paid_balance: Decimal | float | None = None
    promotional_balance: Decimal | float | None = None
    source_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_key: str | None = None


class AgentRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, payload: AgentRunCreate) -> AgentRun:
        run = AgentRun(
            run_key=payload.run_key,
            role=payload.role,
            objective=payload.objective,
            status=payload.status,
            sensitivity=payload.sensitivity,
            as_of_date=payload.as_of_date,
            selection_mode=payload.selection_mode,
            selected_model=payload.selected_model,
            selection_reason=payload.selection_reason,
            total_tokens=0,
            total_estimated_cost_usd=0.0,
            metadata_json=payload.metadata,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def update_run(
        self,
        run_id: int,
        *,
        status: str,
        total_tokens: int,
        total_estimated_cost_usd: float,
        metadata: dict[str, Any] | None = None,
        selection_reason: str | None = None,
    ) -> AgentRun:
        run = self._session.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")
        run.status = status
        run.total_tokens = total_tokens
        run.total_estimated_cost_usd = total_estimated_cost_usd
        if metadata is not None:
            run.metadata_json = metadata
        if selection_reason is not None:
            run.selection_reason = selection_reason
        self._session.flush()
        return run

    def record_tool_call(self, payload: ToolCallRecordCreate) -> ToolCallRecord:
        record = ToolCallRecord(
            run_id=payload.run_id,
            call_id=payload.call_id,
            tool_name=payload.tool_name,
            status=payload.status,
            arguments_json=payload.arguments,
            output_json=payload.output,
            error_code=payload.error_code,
            latency_ms=payload.latency_ms,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def record_model_call(self, payload: ModelCallCreate) -> ModelCall:
        record = ModelCall(
            run_id=payload.run_id,
            provider=payload.provider,
            model=payload.model,
            deployment=payload.deployment,
            serving_engine=payload.serving_engine,
            prompt_tokens=payload.prompt_tokens,
            completion_tokens=payload.completion_tokens,
            estimated_cost_usd=payload.estimated_cost_usd,
            latency_ms=payload.latency_ms,
            success=payload.success,
        )
        self._session.add(record)
        self._session.flush()
        # Keep local deterministic calls in the deletable ModelCall trace for
        # debugging, but never present their word-count approximation as paid
        # provider API usage.
        if payload.deployment.lower() != "local":
            self._session.add(
                ApiUsageLedger(
                    usage_key=f"runtime:{uuid4().hex}",
                    run_id_snapshot=payload.run_id,
                    model_call_id_snapshot=record.id,
                    provider=payload.provider,
                    model=payload.model,
                    deployment=payload.deployment,
                    serving_engine=payload.serving_engine,
                    prompt_tokens=payload.prompt_tokens,
                    completion_tokens=payload.completion_tokens,
                    request_count=max(1, payload.request_count),
                    input_cost_per_million_usd=payload.input_cost_per_million_usd,
                    output_cost_per_million_usd=payload.output_cost_per_million_usd,
                    estimated_cost_usd=payload.estimated_cost_usd,
                    latency_ms=payload.latency_ms,
                    success=payload.success,
                    source="runtime",
                )
            )
        self._session.flush()
        return record

    def record_provider_billing_snapshot(
        self,
        payload: ProviderBillingSnapshotCreate,
    ) -> ProviderBillingSnapshot:
        if payload.snapshot_key is None:
            existing_summary = self._session.scalar(
                select(ProviderBillingSnapshot).where(
                    ProviderBillingSnapshot.provider == payload.provider,
                    ProviderBillingSnapshot.period_start == payload.period_start,
                    ProviderBillingSnapshot.period_end == payload.period_end,
                    ProviderBillingSnapshot.currency == payload.currency.upper(),
                    ProviderBillingSnapshot.actual_cost == payload.actual_cost,
                    ProviderBillingSnapshot.total_tokens == payload.total_tokens,
                    ProviderBillingSnapshot.request_count == payload.request_count,
                    ProviderBillingSnapshot.source_reference
                    == payload.source_reference,
                )
            )
            if existing_summary is not None:
                return existing_summary
        snapshot_key = payload.snapshot_key or f"provider:{uuid4().hex}"
        existing = self._session.scalar(
            select(ProviderBillingSnapshot).where(
                ProviderBillingSnapshot.snapshot_key == snapshot_key
            )
        )
        if existing is not None:
            return existing
        snapshot = ProviderBillingSnapshot(
            snapshot_key=snapshot_key,
            provider=payload.provider,
            period_start=payload.period_start,
            period_end=payload.period_end,
            currency=payload.currency.upper(),
            actual_cost=payload.actual_cost,
            total_tokens=payload.total_tokens,
            request_count=payload.request_count,
            source_reference=payload.source_reference,
            metadata_json=payload.metadata,
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def record_provider_account_snapshot(
        self,
        payload: ProviderAccountSnapshotCreate,
    ) -> ProviderAccountSnapshot:
        snapshot_key = payload.snapshot_key or f"provider-account:{uuid4().hex}"
        existing = self._session.scalar(
            select(ProviderAccountSnapshot).where(
                ProviderAccountSnapshot.snapshot_key == snapshot_key
            )
        )
        if existing is not None:
            return existing
        snapshot = ProviderAccountSnapshot(
            snapshot_key=snapshot_key,
            provider=payload.provider,
            billing_tier=payload.billing_tier,
            billing_status=payload.billing_status,
            currency=(payload.currency.upper() if payload.currency else None),
            available_balance=payload.available_balance,
            paid_balance=payload.paid_balance,
            promotional_balance=payload.promotional_balance,
            source_reference=payload.source_reference,
            metadata_json=payload.metadata,
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def record_claim(self, payload: ClaimCreate) -> Claim:
        claim = Claim(
            report_id=payload.report_id,
            run_id=payload.run_id,
            claim_text=payload.claim_text,
            confidence=payload.confidence,
            evidence_ids_json=payload.evidence_ids,
            relations_json=payload.relations,
        )
        self._session.add(claim)
        self._session.flush()
        return claim

    def record_search_trace(
        self,
        *,
        run_id: int,
        search: dict[str, Any],
        result_rows: list[dict[str, Any]],
    ) -> None:
        """Persist normalized query-to-evidence relations, not copied source text."""

        mode = str(search.get("mode") or "unknown")[:16]
        final_by_chunk = {
            row["chunk_id"]: row
            for row in result_rows
            if isinstance(row.get("chunk_id"), int)
        }
        accepted_chunk_ids = set(final_by_chunk)
        queries = search.get("queries")
        if not isinstance(queries, list):
            return
        for query_data in queries:
            if not isinstance(query_data, dict):
                continue
            chunk_ids = query_data.get("result_chunk_ids")
            if not isinstance(chunk_ids, list):
                chunk_ids = []
            query_record = EvidenceLedgerQuery(
                run_id=run_id,
                round_number=int(query_data.get("round") or 1),
                target_slot=str(query_data.get("target_slot") or "unknown")[:48],
                query_text=str(query_data.get("query") or ""),
                search_mode=mode,
                channel_counts_json=(
                    query_data.get("channel_counts")
                    if isinstance(query_data.get("channel_counts"), dict)
                    else {}
                ),
                result_count=len(chunk_ids),
            )
            self._session.add(query_record)
            self._session.flush()
            for chunk_id in dict.fromkeys(chunk_ids):
                if not isinstance(chunk_id, int) or chunk_id not in final_by_chunk:
                    continue
                chunk = self._session.get(Chunk, chunk_id)
                if chunk is None:
                    continue
                result = final_by_chunk[chunk_id]
                self._session.add(
                    EvidenceLedgerLink(
                        run_id=run_id,
                        query_id=query_record.id,
                        chunk_id=chunk_id,
                        evidence_item_id=chunk.evidence_item_id,
                        accepted=chunk_id in accepted_chunk_ids,
                        fused_score=_optional_float(
                            result.get("fused_score") or result.get("score")
                        ),
                        match_signals_json=(
                            result.get("match_signals")
                            if isinstance(result.get("match_signals"), list)
                            else []
                        ),
                        channel_ranks_json=(
                            result.get("channel_ranks")
                            if isinstance(result.get("channel_ranks"), dict)
                            else {}
                        ),
                    )
                )
        self._session.flush()

    def list_runs(self, *, limit: int = 50, offset: int = 0) -> list[AgentRun]:
        return list(
            self._session.scalars(
                select(AgentRun)
                .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def count_runs(self) -> int:
        return int(self._session.scalar(select(func.count(AgentRun.id))) or 0)

    def run_totals(self) -> tuple[int, int, float, int]:
        row = self._session.execute(
            select(
                func.count(AgentRun.id),
                func.coalesce(func.sum(AgentRun.total_tokens), 0),
                func.coalesce(func.sum(AgentRun.total_estimated_cost_usd), 0),
                func.coalesce(
                    func.sum(case((AgentRun.status != "complete", 1), else_=0)),
                    0,
                ),
            )
        ).one()
        return int(row[0]), int(row[1]), float(row[2]), int(row[3])

    def prune_runs_by_role(
        self,
        *,
        role: str,
        keep_latest: int,
        max_age_days: int | None = None,
    ) -> int:
        """Keep a bounded recent audit window for one run role.

        Portfolio market traces do not own reports, claims, or evidence-ledger rows.
        Deleting their model/tool telemetry first also keeps SQLite tests independent
        of foreign-key pragma configuration; PostgreSQL retains the database cascades.
        """

        keep = max(1, keep_latest)
        obsolete_ids = set(
            self._session.scalars(
                select(AgentRun.id)
                .where(AgentRun.role == role)
                .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
                .offset(keep)
            )
        )
        if max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, max_age_days))
            obsolete_ids.update(
                self._session.scalars(
                    select(AgentRun.id).where(
                        AgentRun.role == role,
                        AgentRun.created_at < cutoff,
                    )
                )
            )
        if not obsolete_ids:
            return 0
        self._session.execute(
            delete(ModelCall).where(ModelCall.run_id.in_(obsolete_ids))
        )
        self._session.execute(
            delete(ToolCallRecord).where(ToolCallRecord.run_id.in_(obsolete_ids))
        )
        self._session.execute(delete(AgentRun).where(AgentRun.id.in_(obsolete_ids)))
        self._session.flush()
        return len(obsolete_ids)

    def get_run(self, run_id: int) -> AgentRun | None:
        return self._session.get(AgentRun, run_id)

    def count_model_calls(self) -> int:
        return int(self._session.scalar(select(func.count(ModelCall.id))) or 0)

    def count_tool_calls(self) -> int:
        return int(self._session.scalar(select(func.count(ToolCallRecord.id))) or 0)

    def model_call_breakdown(self) -> list[ModelCallAggregate]:
        rows = self._session.execute(
            select(
                ModelCall.provider,
                ModelCall.model,
                ModelCall.deployment,
                func.count(ModelCall.id),
                func.coalesce(func.sum(ModelCall.prompt_tokens), 0),
                func.coalesce(func.sum(ModelCall.completion_tokens), 0),
                func.coalesce(func.sum(ModelCall.estimated_cost_usd), 0),
                func.avg(ModelCall.latency_ms),
            )
            .where(func.lower(ModelCall.deployment) != "local")
            .group_by(ModelCall.provider, ModelCall.model, ModelCall.deployment)
            .order_by(func.count(ModelCall.id).desc())
        ).all()
        return [
            ModelCallAggregate(
                provider=str(row[0]),
                model=str(row[1]),
                deployment=str(row[2]),
                call_count=int(row[3]),
                prompt_tokens=int(row[4]),
                completion_tokens=int(row[5]),
                total_estimated_cost_usd=float(row[6]),
                avg_latency_ms=float(row[7]) if row[7] is not None else None,
            )
            for row in rows
        ]

    def api_usage_totals(self) -> UsageTotals:
        row = self._session.execute(
            select(
                func.coalesce(func.sum(ApiUsageLedger.request_count), 0),
                func.coalesce(func.sum(ApiUsageLedger.prompt_tokens), 0),
                func.coalesce(func.sum(ApiUsageLedger.completion_tokens), 0),
                func.coalesce(func.sum(ApiUsageLedger.estimated_cost_usd), 0),
                func.min(ApiUsageLedger.created_at),
                func.max(ApiUsageLedger.created_at),
            ).where(func.lower(ApiUsageLedger.deployment) != "local")
        ).one()
        return UsageTotals(
            call_count=int(row[0]),
            prompt_tokens=int(row[1]),
            completion_tokens=int(row[2]),
            total_estimated_cost_usd=float(row[3]),
            first_recorded_at=row[4],
            last_recorded_at=row[5],
        )

    def retained_model_usage_totals(self) -> UsageTotals:
        row = self._session.execute(
            select(
                func.count(ModelCall.id),
                func.coalesce(func.sum(ModelCall.prompt_tokens), 0),
                func.coalesce(func.sum(ModelCall.completion_tokens), 0),
                func.coalesce(func.sum(ModelCall.estimated_cost_usd), 0),
                func.min(ModelCall.created_at),
                func.max(ModelCall.created_at),
            ).where(func.lower(ModelCall.deployment) != "local")
        ).one()
        return UsageTotals(
            call_count=int(row[0]),
            prompt_tokens=int(row[1]),
            completion_tokens=int(row[2]),
            total_estimated_cost_usd=float(row[3]),
            first_recorded_at=row[4],
            last_recorded_at=row[5],
        )

    def api_usage_breakdown(self) -> list[ApiUsageAggregate]:
        rows = self._session.execute(
            select(
                ApiUsageLedger.provider,
                ApiUsageLedger.model,
                ApiUsageLedger.deployment,
                ApiUsageLedger.input_cost_per_million_usd,
                ApiUsageLedger.output_cost_per_million_usd,
                func.coalesce(func.sum(ApiUsageLedger.request_count), 0),
                func.coalesce(func.sum(ApiUsageLedger.prompt_tokens), 0),
                func.coalesce(func.sum(ApiUsageLedger.completion_tokens), 0),
                func.coalesce(func.sum(ApiUsageLedger.estimated_cost_usd), 0),
            )
            .where(func.lower(ApiUsageLedger.deployment) != "local")
            .group_by(
                ApiUsageLedger.provider,
                ApiUsageLedger.model,
                ApiUsageLedger.deployment,
                ApiUsageLedger.input_cost_per_million_usd,
                ApiUsageLedger.output_cost_per_million_usd,
            )
            .order_by(func.sum(ApiUsageLedger.request_count).desc())
        ).all()
        return [
            ApiUsageAggregate(
                provider=str(row[0]),
                model=str(row[1]),
                deployment=str(row[2]),
                input_cost_per_million_usd=(
                    float(row[3]) if row[3] is not None else None
                ),
                output_cost_per_million_usd=(
                    float(row[4]) if row[4] is not None else None
                ),
                call_count=int(row[5]),
                prompt_tokens=int(row[6]),
                completion_tokens=int(row[7]),
                total_estimated_cost_usd=float(row[8]),
            )
            for row in rows
        ]

    def list_provider_billing_snapshots(
        self,
        *,
        limit: int = 20,
    ) -> list[ProviderBillingSnapshot]:
        return list(
            self._session.scalars(
                select(ProviderBillingSnapshot)
                .order_by(
                    ProviderBillingSnapshot.period_end.desc(),
                    ProviderBillingSnapshot.id.desc(),
                )
                .limit(limit)
            )
        )

    def list_latest_provider_account_snapshots(self) -> list[ProviderAccountSnapshot]:
        rows = list(
            self._session.scalars(
                select(ProviderAccountSnapshot).order_by(
                    ProviderAccountSnapshot.created_at.desc(),
                    ProviderAccountSnapshot.id.desc(),
                )
            )
        )
        latest: dict[str, ProviderAccountSnapshot] = {}
        for row in rows:
            latest.setdefault(row.provider, row)
        return list(latest.values())

    def list_model_calls(
        self,
        *,
        run_id: int | None = None,
        run_ids: set[int] | None = None,
    ) -> list[ModelCall]:
        query = select(ModelCall).order_by(ModelCall.created_at.asc())
        if run_id is not None:
            query = query.where(ModelCall.run_id == run_id)
        elif run_ids is not None:
            if not run_ids:
                return []
            query = query.where(ModelCall.run_id.in_(run_ids))
        return list(self._session.scalars(query))

    def list_tool_calls(
        self,
        *,
        run_id: int | None = None,
        run_ids: set[int] | None = None,
    ) -> list[ToolCallRecord]:
        query = select(ToolCallRecord).order_by(ToolCallRecord.created_at.asc())
        if run_id is not None:
            query = query.where(ToolCallRecord.run_id == run_id)
        elif run_ids is not None:
            if not run_ids:
                return []
            query = query.where(ToolCallRecord.run_id.in_(run_ids))
        return list(self._session.scalars(query))

    def list_evidence_ledger_queries(
        self,
        *,
        run_id: int,
    ) -> list[EvidenceLedgerQuery]:
        query = (
            select(EvidenceLedgerQuery)
            .where(EvidenceLedgerQuery.run_id == run_id)
            .order_by(
                EvidenceLedgerQuery.round_number.asc(),
                EvidenceLedgerQuery.id.asc(),
            )
        )
        return list(self._session.scalars(query))

    def list_evidence_ledger_links(
        self,
        *,
        run_id: int,
    ) -> list[EvidenceLedgerLink]:
        query = (
            select(EvidenceLedgerLink)
            .where(EvidenceLedgerLink.run_id == run_id)
            .order_by(EvidenceLedgerLink.id.asc())
        )
        return list(self._session.scalars(query))

    def mark_answer_evidence(
        self,
        *,
        run_id: int,
        evidence_ids: tuple[int, ...],
    ) -> None:
        accepted_ids = set(evidence_ids)
        for link in self.list_evidence_ledger_links(run_id=run_id):
            link.accepted = (
                link.evidence_item_id is not None
                and link.evidence_item_id in accepted_ids
            )
        self._session.flush()


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
