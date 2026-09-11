from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from investment_agent.config import Settings, get_settings
from investment_agent.embeddings import (
    DeterministicHashEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingService,
    GeminiEmbeddingProvider,
)
from investment_agent.harness import AgentLoop, ToolExecutionPolicy, ToolRegistry
from investment_agent.harness.agent_loop import AgentLoopResult
from investment_agent.providers import (
    DeterministicMockModelProvider,
    GeminiModelProvider,
    OpenAICompatibleModelProvider,
)
from investment_agent.providers.types import ModelProvider
from investment_agent.repositories import DocumentRepository
from investment_agent.research.claims import ClaimGenerator, GeneratedClaim
from investment_agent.research.critic import (
    CriticReview,
    EvidenceCritic,
    include_claim_verification,
)
from investment_agent.retrieval import (
    RETRIEVE_EVIDENCE_TOOL,
    make_retrieve_evidence_tool,
)
from investment_agent.retrieval.policy import EvidenceSlotSpec


@dataclass(frozen=True)
class ResearchWorkflowResult:
    agent_result: AgentLoopResult
    critic: CriticReview
    claims: tuple[GeneratedClaim, ...]


class LocalResearchWorkflow:
    """Run retrieval locally and route public answers to an enabled cloud model."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    def run(
        self,
        *,
        query: str,
        sensitivity: str = "internal",
        as_of_date: date | None = None,
        document_id: int | None = None,
        selection_mode: str = "auto",
        requested_model: str | None = None,
        style_context: str | None = None,
        method_slots: tuple[EvidenceSlotSpec, ...] = (),
    ) -> ResearchWorkflowResult:
        embedding_provider = self._make_embedding_provider(
            sensitivity=sensitivity,
            selection_mode=selection_mode,
            requested_model=requested_model,
        )
        self._ensure_document_embeddings(
            embedding_provider,
            document_id=document_id,
        )

        registry = ToolRegistry(
            policy=ToolExecutionPolicy(
                timeout_seconds=self._settings.tool_timeout_ms / 1000,
                max_attempts=self._settings.tool_max_attempts,
                retry_backoff_seconds=self._settings.tool_retry_backoff_ms / 1000,
            )
        )
        registry.register(
            RETRIEVE_EVIDENCE_TOOL,
            make_retrieve_evidence_tool(
                self._session,
                embedding_provider,
                method_slots=method_slots,
            ),
        )

        agent_result = AgentLoop(
            self._session,
            self.model_provider(
                sensitivity=sensitivity,
                selection_mode=selection_mode,
                requested_model=requested_model,
            ),
            registry,
        ).run(
            objective=query,
            sensitivity=sensitivity,
            as_of_date=as_of_date,
            document_id=document_id,
            selection_mode=selection_mode,
            requested_model=requested_model,
            style_context=style_context,
        )
        critic = EvidenceCritic().review_answer(
            answer=agent_result.answer,
            sources=agent_result.sources,
        )
        claims = ClaimGenerator().generate(
            answer=agent_result.answer,
            sources=agent_result.sources,
        )
        critic = include_claim_verification(critic, claims)
        return ResearchWorkflowResult(
            agent_result=agent_result,
            critic=critic,
            claims=claims,
        )

    def model_provider(
        self,
        *,
        sensitivity: str,
        selection_mode: str,
        requested_model: str | None,
    ) -> ModelProvider:
        if selection_mode != "manual" or requested_model in {
            None,
            "local/deterministic-mock-researcher",
        }:
            return DeterministicMockModelProvider()

        manual_gemini = requested_model == f"google/{self._settings.gemini_model}"
        use_gemini = (
            self._settings.enable_cloud_services
            and self._settings.gemini_api_key is not None
            and sensitivity == "public"
            and manual_gemini
        )
        if use_gemini:
            return GeminiModelProvider(
                api_key=self._settings.gemini_api_key or "",
                model=self._settings.gemini_model,
                timeout_ms=self._settings.model_timeout_ms,
                max_attempts=self._settings.model_max_attempts,
                retry_backoff_ms=self._settings.model_retry_backoff_ms,
                input_cost_per_million=self._settings.gemini_input_cost_per_million,
                output_cost_per_million=self._settings.gemini_output_cost_per_million,
            )

        provider_configs = {
            f"deepseek/{self._settings.deepseek_model}": {
                "provider_name": "deepseek",
                "api_key": self._settings.deepseek_api_key,
                "model": self._settings.deepseek_model,
                "base_url": self._settings.deepseek_base_url,
                "serving_engine": "deepseek-api",
                "input_cost_per_million": self._settings.deepseek_input_cost_per_million,
                "output_cost_per_million": self._settings.deepseek_output_cost_per_million,
            },
            f"moonshot/{self._settings.kimi_model}": {
                "provider_name": "moonshot",
                "api_key": self._settings.kimi_api_key,
                "model": self._settings.kimi_model,
                "base_url": self._settings.kimi_base_url,
                "serving_engine": "kimi-api",
                "input_cost_per_million": self._settings.kimi_input_cost_per_million,
                "output_cost_per_million": self._settings.kimi_output_cost_per_million,
            },
        }
        config = provider_configs.get(requested_model or "")
        if (
            config is not None
            and config["api_key"] is not None
            and self._settings.enable_cloud_services
            and sensitivity == "public"
        ):
            return OpenAICompatibleModelProvider(
                **config,
                timeout_ms=(
                    self._settings.kimi_timeout_ms
                    if requested_model == f"moonshot/{self._settings.kimi_model}"
                    else self._settings.model_timeout_ms
                ),
                max_attempts=self._settings.model_max_attempts,
                retry_backoff_ms=self._settings.model_retry_backoff_ms,
            )
        return DeterministicMockModelProvider()

    def _make_embedding_provider(
        self,
        *,
        sensitivity: str,
        selection_mode: str,
        requested_model: str | None,
    ) -> EmbeddingProvider:
        if (
            sensitivity == "public"
            and selection_mode == "manual"
            and requested_model == f"google/{self._settings.gemini_model}"
            and self._settings.enable_cloud_services
            and self._settings.gemini_api_key is not None
        ):
            return GeminiEmbeddingProvider(
                api_key=self._settings.gemini_api_key,
                model=self._settings.gemini_embedding_model,
                dimensions=self._settings.gemini_embedding_dimensions,
                timeout_ms=self._settings.model_timeout_ms,
                max_attempts=self._settings.model_max_attempts,
                retry_backoff_ms=self._settings.model_retry_backoff_ms,
            )
        return DeterministicHashEmbeddingProvider(dimensions=16)

    def _ensure_document_embeddings(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        document_id: int | None,
    ) -> None:
        embedding_service = EmbeddingService(self._session, embedding_provider)
        documents = DocumentRepository(self._session).list_documents()
        if document_id is not None:
            documents = [
                document for document in documents if document.id == document_id
            ]
        for document in documents:
            embedding_service.embed_document_chunks(document.id)
