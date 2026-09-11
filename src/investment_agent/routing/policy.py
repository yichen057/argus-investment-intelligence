from dataclasses import dataclass
from enum import StrEnum

from investment_agent.providers.types import Deployment, ModelProfile


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class Capability(StrEnum):
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    LONG_CONTEXT = "long_context"
    REASONING = "reasoning"


class RoutingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RouteRequest:
    sensitivity: Sensitivity
    required_capabilities: frozenset[Capability]
    redacted: bool = False
    minimum_quality: float = 0.0


class Router:
    """Apply privacy admission before capability and quality selection."""

    def __init__(self, profiles: list[ModelProfile]) -> None:
        self._profiles = tuple(profiles)

    def route(self, request: RouteRequest) -> ModelProfile:
        admitted = [
            profile
            for profile in self._profiles
            if self._sensitivity_allows(profile, request)
        ]
        capable = [
            profile
            for profile in admitted
            if {cap.value for cap in request.required_capabilities}
            <= profile.capabilities
            and profile.quality_score >= request.minimum_quality
        ]
        if not capable:
            raise RoutingError(
                "No model profile satisfies the sensitivity and capability policy"
            )

        return max(
            capable,
            key=lambda profile: (
                profile.quality_score,
                profile.cost_score,
                profile.latency_score,
            ),
        )

    @staticmethod
    def _sensitivity_allows(
        profile: ModelProfile, request: RouteRequest
    ) -> bool:
        if request.sensitivity.value not in profile.allowed_sensitivity:
            return False
        if request.sensitivity is Sensitivity.RESTRICTED:
            return profile.deployment is Deployment.LOCAL
        if request.sensitivity is Sensitivity.INTERNAL and not request.redacted:
            return profile.deployment is Deployment.LOCAL
        return True
