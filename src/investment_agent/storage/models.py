from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    access_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    evidence_items: Mapped[list[EvidenceItem]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class EvidenceItem(TimestampMixin, Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(256))
    page_or_section: Mapped[str | None] = mapped_column(String(256))
    publication_date: Mapped[date | None] = mapped_column(Date)
    data_as_of_date: Mapped[date | None] = mapped_column(Date)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evidence_grade: Mapped[str] = mapped_column(String(32), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    access_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="evidence_items")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="evidence_item", cascade="all, delete-orphan"
    )


class Chunk(TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        Index(
            "ix_chunks_text_fts",
            sql_text("to_tsvector('simple', text)"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="SET NULL"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    evidence_item: Mapped[EvidenceItem | None] = relationship(back_populates="chunks")
    embeddings: Mapped[list[ChunkEmbedding]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )


class ChunkEmbedding(TimestampMixin, Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id", "provider", "model", name="uq_chunk_embeddings_profile"
        ),
        Index(
            "ix_chunk_embeddings_vector_hnsw",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_json: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(768), nullable=True
    )

    chunk: Mapped[Chunk] = relationship(back_populates="embeddings")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    report_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    rendered_html: Mapped[str | None] = mapped_column(Text)

    claims: Mapped[list[Claim]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_ids_json: Mapped[list[int]] = mapped_column(
        JSON, default=list, nullable=False
    )
    relations_json: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    report: Mapped[Report | None] = relationship(back_populates="claims")


class PortfolioSnapshot(TimestampMixin, Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index(
            "ix_portfolio_snapshots_source_active",
            "source_key",
            "source_scope",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_live: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    positions: Mapped[list[PortfolioPosition]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class PortfolioPosition(TimestampMixin, Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), index=True
    )
    source_key: Mapped[str] = mapped_column(
        String(64), nullable=False, default="file_upload", index=True
    )
    source_scope: Mapped[str] = mapped_column(
        String(128), nullable=False, default="manual"
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    market_value: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float | None] = mapped_column(Float)
    account: Mapped[str | None] = mapped_column(String(128))
    import_id: Mapped[str | None] = mapped_column(String(128), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    snapshot: Mapped[PortfolioSnapshot | None] = relationship(
        back_populates="positions"
    )


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_tolerance: Mapped[str] = mapped_column(String(64), nullable=False)
    life_stage: Mapped[str | None] = mapped_column(String(128))
    investment_horizon: Mapped[str | None] = mapped_column(String(128))
    investing_experience: Mapped[str | None] = mapped_column(String(128))
    income_stability: Mapped[str | None] = mapped_column(String(128))
    liquidity_needs: Mapped[str | None] = mapped_column(String(128))
    preferred_style: Mapped[str | None] = mapped_column(String(128))
    preferred_method_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("investment_method_documents.id", ondelete="SET NULL"), index=True
    )
    preferred_method_document_ids_json: Mapped[list[int]] = mapped_column(
        JSON, default=list, nullable=False
    )
    target_allocation_json: Mapped[dict[str, float]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    monthly_net_income: Mapped[float | None] = mapped_column(Float)
    monthly_contribution: Mapped[float | None] = mapped_column(Float)
    monthly_sector_satellite_budget: Mapped[float | None] = mapped_column(Float)
    monthly_total_expenses: Mapped[float | None] = mapped_column(Float)
    primary_financial_priority: Mapped[str | None] = mapped_column(String(256))
    current_age: Mapped[int | None] = mapped_column(Integer)
    planned_retirement_age: Mapped[int | None] = mapped_column(Integer)
    retirement_planning_age: Mapped[int] = mapped_column(
        Integer, default=100, nullable=False
    )
    retirement_monthly_spending: Mapped[float | None] = mapped_column(Float)
    retirement_monthly_income: Mapped[float | None] = mapped_column(Float)
    retirement_current_savings: Mapped[float | None] = mapped_column(Float)
    retirement_income_taxable: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    retirement_inflation_rate: Mapped[float] = mapped_column(
        Float, default=0.025, nullable=False
    )
    retirement_current_tax_rate: Mapped[float | None] = mapped_column(Float)
    retirement_tax_rate: Mapped[float | None] = mapped_column(Float)
    retirement_annual_return: Mapped[float] = mapped_column(
        Float, default=0.05, nullable=False
    )
    retirement_account_type: Mapped[str | None] = mapped_column(String(32))
    retirement_taxable_withdrawal_share: Mapped[float | None] = mapped_column(Float)
    retirement_adjust_contributions_for_inflation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    monthly_essential_expenses: Mapped[float | None] = mapped_column(Float)
    current_cash_savings: Mapped[float | None] = mapped_column(Float)
    emergency_fund_months: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    emergency_fund_target_amount: Mapped[float | None] = mapped_column(Float)
    emergency_fund_build_months: Mapped[int] = mapped_column(
        Integer, default=12, nullable=False
    )
    education_plan: Mapped[str] = mapped_column(
        String(32), default="none", nullable=False
    )
    education_target_year: Mapped[int | None] = mapped_column(Integer)
    education_target_amount: Mapped[float | None] = mapped_column(Float)
    near_term_goal_name: Mapped[str | None] = mapped_column(String(256))
    near_term_goal_amount: Mapped[float | None] = mapped_column(Float)
    near_term_goal_months: Mapped[int | None] = mapped_column(Integer)
    cash_goals_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    retirement_cash_months: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    retirement_cash_target: Mapped[float | None] = mapped_column(Float)
    rebalance_threshold: Mapped[float] = mapped_column(
        Float, default=0.05, nullable=False
    )
    allow_fractional_shares: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    rebalance_preference: Mapped[str] = mapped_column(
        String(32), default="contributions_first", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MarketAlertSettings(TimestampMixin, Base):
    __tablename__ = "market_alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delivery_mode: Mapped[str] = mapped_column(
        String(32), default="preview_only", nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(32), default="holdings", nullable=False
    )
    sensitivity: Mapped[str] = mapped_column(
        String(32), default="standard", nullable=False
    )
    timezone: Mapped[str] = mapped_column(
        String(64), default="America/Los_Angeles", nullable=False
    )
    quiet_hours_start: Mapped[str] = mapped_column(
        String(5), default="21:00", nullable=False
    )
    quiet_hours_end: Mapped[str] = mapped_column(
        String(5), default="07:00", nullable=False
    )
    policy_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class MarketAlertSnapshot(TimestampMixin, Base):
    __tablename__ = "market_alert_snapshots"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_market_alert_deduplication_key"),
        Index("ix_market_alert_symbol_created", "symbol", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="preview", nullable=False
    )
    holding_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    portfolio_weight: Mapped[float] = mapped_column(Float, nullable=False)
    latest_close: Mapped[float] = mapped_column(Float, nullable=False)
    market_as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    holdings_as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    counter_evidence_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    invalidation_conditions_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(128), nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(32))
    feedback_action: Mapped[str | None] = mapped_column(String(256))
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestmentStylePack(TimestampMixin, Base):
    __tablename__ = "investment_style_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class InvestmentMethodDocument(TimestampMixin, Base):
    __tablename__ = "investment_method_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checklist_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    detected_lenses_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    focus_terms_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    selection_mode: Mapped[str] = mapped_column(
        String(32), default="auto", nullable=False
    )
    selected_model: Mapped[str | None] = mapped_column(String(256))
    selection_reason: Mapped[str | None] = mapped_column(Text)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), default=0.0, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class ToolCallRecord(TimestampMixin, Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    output_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class EvidenceLedgerQuery(TimestampMixin, Base):
    __tablename__ = "evidence_ledger_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_slot: Mapped[str] = mapped_column(String(48), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    channel_counts_json: Mapped[dict[str, int]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EvidenceLedgerLink(TimestampMixin, Base):
    __tablename__ = "evidence_ledger_links"
    __table_args__ = (
        UniqueConstraint(
            "query_id",
            "chunk_id",
            name="uq_evidence_ledger_query_chunk",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_ledger_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), index=True
    )
    evidence_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="SET NULL"), index=True
    )
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fused_score: Mapped[float | None] = mapped_column(Float)
    match_signals_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    channel_ranks_json: Mapped[dict[str, int]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class ModelCall(TimestampMixin, Base):
    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    deployment: Mapped[str] = mapped_column(String(64), nullable=False)
    serving_engine: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), default=0.0, nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApiUsageLedger(TimestampMixin, Base):
    """Append-only model API usage independent from deletable Run traces."""

    __tablename__ = "api_usage_ledger"
    __table_args__ = (
        Index("ix_api_usage_ledger_provider_model", "provider", "model"),
        Index("ix_api_usage_ledger_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usage_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # Snapshot identifiers intentionally have no foreign keys. A Run or ModelCall
    # may be deleted while the non-sensitive billing fact remains auditable.
    run_id_snapshot: Mapped[int | None] = mapped_column(Integer, index=True)
    model_call_id_snapshot: Mapped[int | None] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    deployment: Mapped[str] = mapped_column(String(64), nullable=False)
    serving_engine: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input_cost_per_million_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    output_cost_per_million_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), default=0.0, nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="runtime", nullable=False)


class EventAuditRecord(TimestampMixin, Base):
    """Sanitized Kafka consumer projection; never stores a raw event payload."""

    __tablename__ = "event_audit_records"
    __table_args__ = (
        Index("ix_event_audit_records_type_status", "event_type", "status"),
        Index("ix_event_audit_records_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    consumer_group: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    partition: Mapped[int | None] = mapped_column(Integer)
    message_offset: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(128))


class EventConsumerHeartbeat(TimestampMixin, Base):
    """Latest sanitized liveness state for one Kafka consumer group."""

    __tablename__ = "event_consumer_heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumer_group: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    topics_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(128))


class ProviderBillingSnapshot(TimestampMixin, Base):
    """Provider-reported aggregate used for reconciliation, not estimation."""

    __tablename__ = "provider_billing_snapshots"
    __table_args__ = (
        Index(
            "ix_provider_billing_snapshots_provider_period",
            "provider",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    actual_cost: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    request_count: Mapped[int | None] = mapped_column(Integer)
    source_reference: Mapped[str | None] = mapped_column(String(512))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class ProviderAccountSnapshot(TimestampMixin, Base):
    """Point-in-time provider balance or billing-tier status; never a charge."""

    __tablename__ = "provider_account_snapshots"
    __table_args__ = (
        Index(
            "ix_provider_account_snapshots_provider_created",
            "provider",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    billing_tier: Mapped[str | None] = mapped_column(String(64))
    billing_status: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8))
    available_balance: Mapped[float | None] = mapped_column(Numeric(20, 10))
    paid_balance: Mapped[float | None] = mapped_column(Numeric(20, 10))
    promotional_balance: Mapped[float | None] = mapped_column(Numeric(20, 10))
    source_reference: Mapped[str | None] = mapped_column(String(512))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
