import pytest

from investment_agent.providers import Deployment, ModelProfile
from investment_agent.routing import (
    Capability,
    RouteRequest,
    Router,
    RoutingError,
    Sensitivity,
)


def profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            name="local",
            deployment=Deployment.LOCAL,
            allowed_sensitivity=frozenset({"public", "internal", "restricted"}),
            capabilities=frozenset(
                {"extraction", "summarization", "structured_output"}
            ),
            quality_score=0.6,
            cost_score=1.0,
            latency_score=0.7,
        ),
        ModelProfile(
            name="cloud_reasoning",
            deployment=Deployment.CLOUD,
            allowed_sensitivity=frozenset({"public", "internal"}),
            capabilities=frozenset(
                {"tool_calling", "structured_output", "reasoning"}
            ),
            quality_score=0.95,
            cost_score=0.5,
            latency_score=0.6,
        ),
    ]


def test_restricted_context_never_routes_to_cloud() -> None:
    router = Router(profiles())
    request = RouteRequest(
        sensitivity=Sensitivity.RESTRICTED,
        required_capabilities=frozenset({Capability.STRUCTURED_OUTPUT}),
    )

    assert router.route(request).name == "local"


def test_unredacted_internal_context_stays_local() -> None:
    router = Router(profiles())
    request = RouteRequest(
        sensitivity=Sensitivity.INTERNAL,
        required_capabilities=frozenset({Capability.REASONING}),
        redacted=False,
    )

    with pytest.raises(RoutingError):
        router.route(request)


def test_redacted_internal_context_can_use_capable_cloud_profile() -> None:
    router = Router(profiles())
    request = RouteRequest(
        sensitivity=Sensitivity.INTERNAL,
        required_capabilities=frozenset(
            {Capability.REASONING, Capability.STRUCTURED_OUTPUT}
        ),
        redacted=True,
    )

    assert router.route(request).name == "cloud_reasoning"

