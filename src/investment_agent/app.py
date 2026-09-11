from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from investment_agent import __version__
from investment_agent.api.chat import router as chat_router
from investment_agent.api.alerts import router as alerts_router
from investment_agent.api.documents import router as documents_router
from investment_agent.api.evals import router as evals_router
from investment_agent.api.jobs import router as jobs_router
from investment_agent.api.portfolio import router as portfolio_router
from investment_agent.api.profile import router as profile_router
from investment_agent.api.reports import router as reports_router
from investment_agent.api.runs import router as runs_router
from investment_agent.api.style_packs import router as style_packs_router
from investment_agent.config import Settings, get_settings
from investment_agent.integrations.robinhood import RobinhoodSidecarHttpClient
from investment_agent.cloud import (
    RedisJobQueue,
    make_artifact_store,
    make_cache_store,
    make_event_publisher,
)
from investment_agent.observability import configure_observability
from investment_agent.storage import make_engine, make_session_factory


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    mode: str
    etf_selection_engine: str
    external_market_data_enabled: bool
    market_heatmap_enabled: bool
    unified_etf_universe_enabled: bool
    robinhood_enabled: bool
    robinhood_sidecar_configured: bool
    market_data_provider_code: str
    market_data_provider: str


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="Argus API",
        version=__version__,
        description="Local-first investment research API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = resolved_settings
    # Authenticated transports can be injected by the desktop/MCP host. The API
    # never creates a brokerage session or stores brokerage credentials itself.
    app.state.robinhood_gateway = None
    if (
        resolved_settings.enable_external_market_data
        and resolved_settings.enable_robinhood
        and resolved_settings.robinhood_sidecar_url
        and resolved_settings.robinhood_sidecar_token
    ):
        app.state.robinhood_gateway = RobinhoodSidecarHttpClient(
            base_url=resolved_settings.robinhood_sidecar_url,
            bearer_token=resolved_settings.robinhood_sidecar_token,
            timeout_seconds=resolved_settings.tool_timeout_ms / 1000,
        )
    app.state.market_data_source = None
    engine = make_engine(resolved_settings)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.cache_store = make_cache_store(resolved_settings.redis_url)
    app.state.job_queue = (
        RedisJobQueue(resolved_settings.redis_url)
        if resolved_settings.redis_url
        else None
    )
    app.state.event_publisher = make_event_publisher(
        resolved_settings.kafka_bootstrap_servers,
        client_id=resolved_settings.kafka_client_id,
        security_protocol=resolved_settings.kafka_security_protocol,
        sasl_mechanism=resolved_settings.kafka_sasl_mechanism,
        aws_region=resolved_settings.aws_region,
    )
    app.router.add_event_handler("shutdown", app.state.event_publisher.close)
    app.state.artifact_store = make_artifact_store(resolved_settings)
    app.state.tracer_provider = configure_observability(app, engine, resolved_settings)
    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(reports_router)
    app.include_router(portfolio_router)
    app.include_router(alerts_router)
    app.include_router(profile_router)
    app.include_router(style_packs_router)
    app.include_router(runs_router)
    app.include_router(evals_router)
    app.include_router(jobs_router)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="argus-api",
            version=__version__,
            mode=resolved_settings.env,
            etf_selection_engine=resolved_settings.etf_selection_engine,
            external_market_data_enabled=(
                resolved_settings.enable_external_market_data
            ),
            market_heatmap_enabled=resolved_settings.enable_market_heatmap,
            unified_etf_universe_enabled=(
                resolved_settings.enable_unified_etf_universe
            ),
            robinhood_enabled=resolved_settings.enable_robinhood,
            robinhood_sidecar_configured=bool(app.state.robinhood_gateway),
            market_data_provider_code=(
                resolved_settings.market_data_provider_code
            ),
            market_data_provider=resolved_settings.market_data_provider_name,
        )

    @app.get("/health/live", tags=["system"])
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["system"])
    def readiness() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        if not app.state.cache_store.ping():
            raise RuntimeError("Cache readiness check failed")
        return {"status": "ready"}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "investment_agent.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )


if __name__ == "__main__":
    main()
