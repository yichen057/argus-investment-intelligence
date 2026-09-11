from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from investment_agent.config import Settings
from investment_agent.embeddings import DeterministicHashEmbeddingProvider, EmbeddingService
from investment_agent.harness import AgentLoop, Budget, ToolRegistry
from investment_agent.ingestion import LocalFileIngestor
from investment_agent.providers import (
    Deployment,
    DeterministicMockModelProvider,
    ModelProfile,
    ModelResponse,
)
from investment_agent.retrieval import RETRIEVE_EVIDENCE_TOOL, make_retrieve_evidence_tool
from investment_agent.routing import Capability, Router
from investment_agent.storage import (
    AgentRun,
    Base,
    EvidenceLedgerLink,
    EvidenceLedgerQuery,
    ModelCall,
    ToolCallRecord,
    make_engine,
    make_session_factory,
    session_scope,
)


def sqlite_settings(database_url: str) -> Settings:
    return Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=database_url,
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )


def session_factory_for_tmp_db(tmp_path: Path) -> sessionmaker[Session]:
    settings = sqlite_settings(f"sqlite:///{tmp_path / 'argus.db'}")
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_mock_agent_loop_retrieves_evidence_and_records_trace(tmp_path: Path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    session_factory = session_factory_for_tmp_db(tmp_path)
    embedding_provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_scope(session_factory) as session:
        ingest_result = LocalFileIngestor(session).ingest_path(source)
        EmbeddingService(session, embedding_provider).embed_document_chunks(
            ingest_result.document_id
        )
        registry = ToolRegistry()
        registry.register(
            RETRIEVE_EVIDENCE_TOOL,
            make_retrieve_evidence_tool(session, embedding_provider),
        )

        result = AgentLoop(
            session,
            DeterministicMockModelProvider(),
            registry,
        ).run(
            objective="Why might gold benefit when real yields fall?",
            as_of_date=date(2026, 1, 1),
        )

        stored_run = session.get(AgentRun, result.run_id)
        model_calls = list(
            session.scalars(select(ModelCall).where(ModelCall.run_id == result.run_id))
        )
        tool_calls = list(
            session.scalars(
                select(ToolCallRecord).where(ToolCallRecord.run_id == result.run_id)
            )
        )
        ledger_queries = list(
            session.scalars(
                select(EvidenceLedgerQuery).where(
                    EvidenceLedgerQuery.run_id == result.run_id
                )
            )
        )
        ledger_links = list(
            session.scalars(
                select(EvidenceLedgerLink).where(
                    EvidenceLedgerLink.run_id == result.run_id
                )
            )
        )

    assert result.status == "complete"
    assert "Gold demand strengthened" in result.answer
    assert "[evidence:" not in result.answer
    assert result.evidence_ids
    assert result.sources[0].display_name == "gold.md"
    assert result.sources[0].evidence_id == result.evidence_ids[0]
    assert result.iterations == 2
    assert result.total_tokens > 0
    assert stored_run is not None
    assert stored_run.status == "complete"
    assert stored_run.selected_model == "local/deterministic-mock-researcher"
    assert stored_run.selection_reason is not None
    assert "Auto selected local/deterministic-mock-researcher" in stored_run.selection_reason
    assert stored_run.total_tokens == result.total_tokens
    assert stored_run.metadata_json["search"]["evidence_gate"]["decision"] == (
        "supported"
    )
    assert stored_run.metadata_json["search"]["accepted_evidence_ids"] == list(
        result.evidence_ids
    )
    assert len(model_calls) == 2
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == RETRIEVE_EVIDENCE_TOOL
    assert tool_calls[0].status == "ok"
    assert ledger_queries
    assert ledger_links
    assert len(ledger_links) <= sum(query.result_count for query in ledger_queries)
    assert {
        link.evidence_item_id for link in ledger_links if link.accepted
    } == set(result.evidence_ids)
    assert "text" not in tool_calls[0].output_json["results"][0]
    assert "context" not in tool_calls[0].output_json["results"][0]


def test_mock_agent_loop_fails_when_requested_tool_is_unknown(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = AgentLoop(
            session,
            DeterministicMockModelProvider(retrieval_tool_name="missing_tool"),
            ToolRegistry(),
        ).run(objective="Find evidence")
        tool_call = session.scalar(
            select(ToolCallRecord).where(ToolCallRecord.run_id == result.run_id)
        )

    assert result.status == "failed"
    assert result.error_code == "unknown_tool"
    assert tool_call is not None
    assert tool_call.status == "error"
    assert tool_call.error_code == "unknown_tool"


def test_mock_agent_loop_stops_at_max_iterations(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)
    embedding_provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with session_scope(session_factory) as session:
        registry = ToolRegistry()
        registry.register(
            RETRIEVE_EVIDENCE_TOOL,
            make_retrieve_evidence_tool(session, embedding_provider),
        )
        result = AgentLoop(
            session,
            DeterministicMockModelProvider(),
            registry,
            max_iterations=1,
        ).run(objective="Find evidence")

    assert result.status == "failed"
    assert result.error_code == "max_iterations_exceeded"
    assert result.iterations == 1


def test_mock_agent_loop_records_budget_exceeded(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = AgentLoop(
            session,
            DeterministicMockModelProvider(),
            ToolRegistry(),
            budget=Budget(max_tokens=1, max_usd=1.0),
        ).run(objective="Find evidence")
        stored_run = session.get(AgentRun, result.run_id)
        model_calls = list(
            session.scalars(select(ModelCall).where(ModelCall.run_id == result.run_id))
        )

    assert result.status == "budget_exceeded"
    assert result.error_code == "budget_exceeded"
    assert result.total_tokens == 0
    assert stored_run is not None
    assert stored_run.status == "budget_exceeded"
    assert len(model_calls) == 1


def test_agent_loop_records_routing_failure_before_model_calls(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)
    cloud_only_profile = ModelProfile(
        name="cloud/mock",
        deployment=Deployment.CLOUD,
        allowed_sensitivity=frozenset({"public", "internal"}),
        capabilities=frozenset(
            {
                Capability.TOOL_CALLING.value,
                Capability.STRUCTURED_OUTPUT.value,
            }
        ),
        quality_score=0.9,
        cost_score=0.4,
        latency_score=0.5,
    )

    with session_scope(session_factory) as session:
        result = AgentLoop(
            session,
            DeterministicMockModelProvider(),
            ToolRegistry(),
            model_profile=cloud_only_profile,
            router=Router([cloud_only_profile]),
        ).run(
            objective="Find evidence",
            sensitivity="restricted",
        )
        stored_run = session.get(AgentRun, result.run_id)
        model_calls = list(
            session.scalars(select(ModelCall).where(ModelCall.run_id == result.run_id))
        )
        tool_calls = list(
            session.scalars(
                select(ToolCallRecord).where(ToolCallRecord.run_id == result.run_id)
            )
        )

    assert result.status == "routing_failed"
    assert result.error_code == "routing_failed"
    assert result.iterations == 0
    assert stored_run is not None
    assert stored_run.status == "routing_failed"
    assert stored_run.selected_model is None
    assert stored_run.selection_reason is not None
    assert "No model profile satisfies" in stored_run.selection_reason
    assert model_calls == []
    assert tool_calls == []


def test_agent_loop_records_manual_model_selection(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = AgentLoop(
            session,
            DeterministicMockModelProvider(),
            ToolRegistry(),
        ).run(
            objective="Find evidence",
            selection_mode="manual",
            requested_model="local/deterministic-mock-researcher",
        )
        stored_run = session.get(AgentRun, result.run_id)

    assert stored_run is not None
    assert stored_run.selection_mode == "manual"
    assert stored_run.selected_model == "local/deterministic-mock-researcher"
    assert stored_run.selection_reason is not None
    assert "Manually selected local/deterministic-mock-researcher" in (
        stored_run.selection_reason
    )


def test_agent_loop_rejects_unavailable_manual_model(tmp_path: Path) -> None:
    session_factory = session_factory_for_tmp_db(tmp_path)

    with session_scope(session_factory) as session:
        result = AgentLoop(
            session,
            DeterministicMockModelProvider(),
            ToolRegistry(),
        ).run(
            objective="Find evidence",
            selection_mode="manual",
            requested_model="google/not-configured",
        )

    assert result.status == "routing_failed"
    assert result.error_code == "model_not_available"


def test_agent_loop_marks_failed_model_response_as_failed_run(tmp_path: Path) -> None:
    class FailingProvider:
        provider_name = "google"
        model_name = "gemini-test"
        deployment = Deployment.CLOUD
        serving_engine = "gemini-api"

        def generate(self, request):
            return ModelResponse(
                provider=self.provider_name,
                model=self.model_name,
                deployment=self.deployment,
                serving_engine=self.serving_engine,
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                estimated_cost_usd=0.0,
                success=False,
                error_code="model_provider_error",
            )

    session_factory = session_factory_for_tmp_db(tmp_path)
    with session_scope(session_factory) as session:
        result = AgentLoop(
            session,
            FailingProvider(),
            ToolRegistry(),
        ).run(objective="Find evidence", sensitivity="public")
        stored_run = session.get(AgentRun, result.run_id)
        model_call = session.scalar(
            select(ModelCall).where(ModelCall.run_id == result.run_id)
        )

    assert result.status == "failed"
    assert result.error_code == "model_provider_error"
    assert stored_run is not None
    assert stored_run.status == "failed"
    assert model_call is not None
    assert model_call.success is False
