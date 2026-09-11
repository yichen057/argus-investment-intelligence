"""Evidence retrieval services with lazy loading for dependency-heavy adapters."""

from typing import Any

from investment_agent.retrieval.constants import RETRIEVE_EVIDENCE_TOOL
from investment_agent.retrieval.evidence_gate import (
    EvidenceDecision,
    EvidenceGate,
    EvidenceGateResult,
)
from investment_agent.retrieval.policy import (
    AdaptiveSearchService,
    DeterministicComplexityPolicy,
    EvidenceSlotSpec,
    SearchMode,
)

__all__ = [
    "RETRIEVE_EVIDENCE_TOOL",
    "AdaptiveSearchService",
    "DeterministicComplexityPolicy",
    "EvidenceDecision",
    "EvidenceGate",
    "EvidenceGateResult",
    "EvidenceSlotSpec",
    "HybridRetrievalService",
    "RetrievalResult",
    "SearchMode",
    "VectorRetrievalService",
    "make_retrieve_evidence_tool",
]


def __getattr__(name: str) -> Any:
    """Load repository/embedding-dependent retrieval components only when requested."""

    if name == "HybridRetrievalService":
        from investment_agent.retrieval.hybrid import HybridRetrievalService

        return HybridRetrievalService
    if name == "make_retrieve_evidence_tool":
        from investment_agent.retrieval.tool import make_retrieve_evidence_tool

        return make_retrieve_evidence_tool
    if name in {"RetrievalResult", "VectorRetrievalService"}:
        from investment_agent.retrieval.vector import (
            RetrievalResult,
            VectorRetrievalService,
        )

        return {
            "RetrievalResult": RetrievalResult,
            "VectorRetrievalService": VectorRetrievalService,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
