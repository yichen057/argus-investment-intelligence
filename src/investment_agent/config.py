from __future__ import annotations

import os
from dataclasses import dataclass

from investment_agent.market_data import normalize_market_data_provider


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _choice(value: str | None, *, default: str, allowed: set[str]) -> str:
    normalized = (value or default).strip().lower()
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"Expected one of {choices}; received {normalized!r}.")
    return normalized


@dataclass(frozen=True)
class Settings:
    env: str
    api_host: str
    api_port: int
    api_reload: bool
    cors_origins: tuple[str, ...]
    database_url: str
    enable_cloud_services: bool
    enable_gmail: bool
    enable_robinhood: bool
    default_model_selection_mode: str
    self_hosted_model_base_url: str | None
    self_hosted_model_name: str | None
    enable_external_market_data: bool = False
    market_data_provider_code: str = "01"
    market_data_provider_key: str = "robinhood"
    market_data_provider_name: str = "Robinhood Market Data"
    enable_market_heatmap: bool = False
    enable_unified_etf_universe: bool = False
    robinhood_sidecar_url: str | None = None
    robinhood_sidecar_token: str | None = None
    robinhood_enable_historicals: bool = False
    model_provider: str = "auto"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 768
    model_timeout_ms: int = 20_000
    model_max_attempts: int = 3
    model_retry_backoff_ms: int = 100
    market_analysis_timeout_ms: int = 60_000
    market_analysis_max_attempts: int = 1
    market_analysis_max_output_tokens: int = 1_600
    market_analysis_trace_retention_count: int = 50
    market_analysis_trace_retention_days: int = 30
    etf_selection_engine: str = "deterministic"
    gemini_input_cost_per_million: float = 0.25
    gemini_output_cost_per_million: float = 1.50
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_input_cost_per_million: float = 0.14
    deepseek_output_cost_per_million: float = 0.28
    deepseek_pro_model: str = "deepseek-v4-pro"
    deepseek_pro_input_cost_per_million: float = 0.435
    deepseek_pro_output_cost_per_million: float = 0.87
    kimi_api_key: str | None = None
    kimi_model: str = "kimi-k2.6"
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_timeout_ms: int = 60_000
    kimi_input_cost_per_million: float = 0.95
    kimi_output_cost_per_million: float = 4.00
    kimi_candidate_model: str | None = None
    kimi_candidate_input_cost_per_million: float = 0.0
    kimi_candidate_output_cost_per_million: float = 0.0
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_input_cost_per_million: float = 5.0
    openai_output_cost_per_million: float = 30.0
    model_benchmark_max_cost_usd: float = 0.10
    exa_api_key: str | None = None
    exa_base_url: str = "https://api.exa.ai"
    exa_search_type: str = "auto"
    exa_timeout_ms: int = 15_000
    exa_max_results: int = 8
    exa_highlight_max_characters: int = 2_000
    exa_search_cost_per_request: float = 0.007
    web_search_max_calls: int = 2
    tool_timeout_ms: int = 10_000
    tool_max_attempts: int = 3
    tool_retry_backoff_ms: int = 100
    document_upload_max_bytes: int = 25 * 1024 * 1024
    document_pdf_max_pages: int = 500
    document_extracted_text_max_characters: int = 2_000_000
    document_extraction_timeout_seconds: float = 90.0
    document_extraction_warning_rss_bytes: int = 1024 * 1024 * 1024
    document_extraction_max_rss_bytes: int = 1536 * 1024 * 1024
    document_resource_poll_interval_ms: int = 500
    document_resource_terminate_grace_seconds: float = 5.0
    document_admission_memory_ratio: float = 0.70
    document_upload_root: str = "data/uploads"
    redis_url: str | None = None
    kafka_bootstrap_servers: str | None = None
    kafka_client_id: str = "argus"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_consumer_group: str = "argus-audit-metrics-v1"
    kafka_consumer_max_attempts: int = 3
    kafka_consumer_retry_backoff_ms: int = 100
    kafka_consumer_poll_timeout_ms: int = 1000
    kafka_consumer_stale_after_seconds: int = 15
    kafka_audit_retention_count: int = 5_000
    kafka_audit_retention_days: int = 30
    event_consumer_health_file: str = "/tmp/argus-event-consumer.live"
    s3_bucket: str | None = None
    s3_prefix: str = "argus"
    aws_region: str = "us-west-2"
    otel_exporter_otlp_endpoint: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        (
            market_data_provider_code,
            market_data_provider_key,
            market_data_provider_name,
        ) = normalize_market_data_provider(os.getenv("ARGUS_MARKET_DATA_PROVIDER"))
        return cls(
            env=os.getenv("ARGUS_ENV", "development"),
            api_host=os.getenv("ARGUS_API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("ARGUS_API_PORT", "8000")),
            api_reload=_truthy(os.getenv("ARGUS_API_RELOAD")),
            cors_origins=_csv(
                os.getenv("ARGUS_CORS_ORIGINS"),
                default=("http://localhost:5173", "http://127.0.0.1:5173"),
            ),
            database_url=os.getenv(
                "ARGUS_DATABASE_URL",
                "postgresql+psycopg://argus:argus@localhost:5432/argus",
            ),
            enable_cloud_services=_truthy(os.getenv("ARGUS_ENABLE_CLOUD_SERVICES")),
            enable_gmail=_truthy(os.getenv("ARGUS_ENABLE_GMAIL")),
            enable_robinhood=_truthy(os.getenv("ARGUS_ENABLE_ROBINHOOD")),
            default_model_selection_mode=os.getenv(
                "ARGUS_MODEL_SELECTION_MODE", "auto"
            ),
            self_hosted_model_base_url=os.getenv("ARGUS_SELF_HOSTED_MODEL_BASE_URL"),
            self_hosted_model_name=os.getenv("ARGUS_SELF_HOSTED_MODEL_NAME"),
            enable_external_market_data=_truthy(
                os.getenv("ARGUS_ENABLE_EXTERNAL_MARKET_DATA")
            ),
            market_data_provider_code=market_data_provider_code,
            market_data_provider_key=market_data_provider_key,
            market_data_provider_name=market_data_provider_name,
            enable_market_heatmap=_truthy(
                os.getenv("ARGUS_ENABLE_MARKET_HEATMAP")
            ),
            enable_unified_etf_universe=_truthy(
                os.getenv("ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE")
            ),
            robinhood_sidecar_url=(
                os.getenv("ARGUS_ROBINHOOD_SIDECAR_URL") or None
            ),
            robinhood_sidecar_token=(
                os.getenv("ARGUS_ROBINHOOD_SIDECAR_TOKEN") or None
            ),
            robinhood_enable_historicals=_truthy(
                os.getenv("ARGUS_ROBINHOOD_ENABLE_HISTORICALS")
            ),
            model_provider=os.getenv("ARGUS_MODEL_PROVIDER", "auto").strip().lower(),
            gemini_api_key=os.getenv("ARGUS_GEMINI_API_KEY") or None,
            gemini_model=os.getenv("ARGUS_GEMINI_MODEL", "gemini-3.1-flash-lite"),
            gemini_embedding_model=os.getenv(
                "ARGUS_GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
            ),
            gemini_embedding_dimensions=int(
                os.getenv("ARGUS_GEMINI_EMBEDDING_DIMENSIONS", "768")
            ),
            model_timeout_ms=int(
                os.getenv(
                    "ARGUS_MODEL_TIMEOUT_MS",
                    os.getenv("ARGUS_GEMINI_TIMEOUT_MS", "20000"),
                )
            ),
            model_max_attempts=int(
                os.getenv(
                    "ARGUS_MODEL_MAX_ATTEMPTS",
                    os.getenv("ARGUS_GEMINI_MAX_ATTEMPTS", "3"),
                )
            ),
            model_retry_backoff_ms=int(
                os.getenv("ARGUS_MODEL_RETRY_BACKOFF_MS", "100")
            ),
            market_analysis_timeout_ms=int(
                os.getenv("ARGUS_MARKET_ANALYSIS_TIMEOUT_MS", "60000")
            ),
            market_analysis_max_attempts=int(
                os.getenv("ARGUS_MARKET_ANALYSIS_MAX_ATTEMPTS", "1")
            ),
            market_analysis_max_output_tokens=int(
                os.getenv("ARGUS_MARKET_ANALYSIS_MAX_OUTPUT_TOKENS", "1600")
            ),
            market_analysis_trace_retention_count=max(
                1,
                int(os.getenv("ARGUS_MARKET_ANALYSIS_TRACE_RETENTION_COUNT", "50")),
            ),
            market_analysis_trace_retention_days=max(
                1,
                int(os.getenv("ARGUS_MARKET_ANALYSIS_TRACE_RETENTION_DAYS", "30")),
            ),
            etf_selection_engine=_choice(
                os.getenv("ARGUS_ETF_SELECTION_ENGINE"),
                default="deterministic",
                allowed={"deterministic", "model"},
            ),
            gemini_input_cost_per_million=float(
                os.getenv("ARGUS_GEMINI_INPUT_COST_PER_MILLION", "0.25")
            ),
            gemini_output_cost_per_million=float(
                os.getenv("ARGUS_GEMINI_OUTPUT_COST_PER_MILLION", "1.50")
            ),
            deepseek_api_key=os.getenv("ARGUS_DEEPSEEK_API_KEY") or None,
            deepseek_model=os.getenv("ARGUS_DEEPSEEK_MODEL", "deepseek-v4-flash"),
            deepseek_base_url=os.getenv(
                "ARGUS_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ),
            deepseek_input_cost_per_million=float(
                os.getenv("ARGUS_DEEPSEEK_INPUT_COST_PER_MILLION", "0.14")
            ),
            deepseek_output_cost_per_million=float(
                os.getenv("ARGUS_DEEPSEEK_OUTPUT_COST_PER_MILLION", "0.28")
            ),
            deepseek_pro_model=os.getenv("ARGUS_DEEPSEEK_PRO_MODEL", "deepseek-v4-pro"),
            deepseek_pro_input_cost_per_million=float(
                os.getenv("ARGUS_DEEPSEEK_PRO_INPUT_COST_PER_MILLION", "0.435")
            ),
            deepseek_pro_output_cost_per_million=float(
                os.getenv("ARGUS_DEEPSEEK_PRO_OUTPUT_COST_PER_MILLION", "0.87")
            ),
            kimi_api_key=os.getenv("ARGUS_KIMI_API_KEY") or None,
            kimi_model=os.getenv("ARGUS_KIMI_MODEL", "kimi-k2.6"),
            kimi_base_url=os.getenv(
                "ARGUS_KIMI_BASE_URL", "https://api.moonshot.ai/v1"
            ),
            kimi_timeout_ms=int(os.getenv("ARGUS_KIMI_TIMEOUT_MS", "60000")),
            kimi_input_cost_per_million=float(
                os.getenv("ARGUS_KIMI_INPUT_COST_PER_MILLION", "0.95")
            ),
            kimi_output_cost_per_million=float(
                os.getenv("ARGUS_KIMI_OUTPUT_COST_PER_MILLION", "4.00")
            ),
            kimi_candidate_model=os.getenv("ARGUS_KIMI_CANDIDATE_MODEL") or None,
            kimi_candidate_input_cost_per_million=float(
                os.getenv("ARGUS_KIMI_CANDIDATE_INPUT_COST_PER_MILLION", "0")
            ),
            kimi_candidate_output_cost_per_million=float(
                os.getenv("ARGUS_KIMI_CANDIDATE_OUTPUT_COST_PER_MILLION", "0")
            ),
            openai_api_key=os.getenv("ARGUS_OPENAI_API_KEY") or None,
            openai_model=os.getenv("ARGUS_OPENAI_MODEL", "gpt-5.5"),
            openai_base_url=os.getenv(
                "ARGUS_OPENAI_BASE_URL", "https://api.openai.com/v1"
            ),
            openai_input_cost_per_million=float(
                os.getenv("ARGUS_OPENAI_INPUT_COST_PER_MILLION", "5.0")
            ),
            openai_output_cost_per_million=float(
                os.getenv("ARGUS_OPENAI_OUTPUT_COST_PER_MILLION", "30.0")
            ),
            model_benchmark_max_cost_usd=float(
                os.getenv("ARGUS_MODEL_BENCHMARK_MAX_COST_USD", "0.10")
            ),
            exa_api_key=os.getenv("ARGUS_EXA_API_KEY") or None,
            exa_base_url=os.getenv("ARGUS_EXA_BASE_URL", "https://api.exa.ai"),
            exa_search_type=os.getenv("ARGUS_EXA_SEARCH_TYPE", "auto"),
            exa_timeout_ms=int(os.getenv("ARGUS_EXA_TIMEOUT_MS", "15000")),
            exa_max_results=int(os.getenv("ARGUS_EXA_MAX_RESULTS", "8")),
            exa_highlight_max_characters=int(
                os.getenv("ARGUS_EXA_HIGHLIGHT_MAX_CHARACTERS", "2000")
            ),
            exa_search_cost_per_request=float(
                os.getenv("ARGUS_EXA_SEARCH_COST_PER_REQUEST", "0.007")
            ),
            web_search_max_calls=int(os.getenv("ARGUS_WEB_SEARCH_MAX_CALLS", "2")),
            tool_timeout_ms=int(os.getenv("ARGUS_TOOL_TIMEOUT_MS", "10000")),
            tool_max_attempts=int(os.getenv("ARGUS_TOOL_MAX_ATTEMPTS", "3")),
            tool_retry_backoff_ms=int(os.getenv("ARGUS_TOOL_RETRY_BACKOFF_MS", "100")),
            document_upload_max_bytes=int(
                os.getenv("ARGUS_DOCUMENT_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024))
            ),
            document_pdf_max_pages=int(
                os.getenv("ARGUS_DOCUMENT_PDF_MAX_PAGES", "500")
            ),
            document_extracted_text_max_characters=int(
                os.getenv("ARGUS_DOCUMENT_EXTRACTED_TEXT_MAX_CHARACTERS", "2000000")
            ),
            document_extraction_timeout_seconds=float(
                os.getenv("ARGUS_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS", "90")
            ),
            document_extraction_warning_rss_bytes=int(
                os.getenv(
                    "ARGUS_DOCUMENT_EXTRACTION_WARNING_RSS_BYTES",
                    str(1024 * 1024 * 1024),
                )
            ),
            document_extraction_max_rss_bytes=int(
                os.getenv(
                    "ARGUS_DOCUMENT_EXTRACTION_MAX_RSS_BYTES",
                    str(1536 * 1024 * 1024),
                )
            ),
            document_resource_poll_interval_ms=int(
                os.getenv("ARGUS_DOCUMENT_RESOURCE_POLL_INTERVAL_MS", "500")
            ),
            document_resource_terminate_grace_seconds=float(
                os.getenv("ARGUS_DOCUMENT_RESOURCE_TERMINATE_GRACE_SECONDS", "5")
            ),
            document_admission_memory_ratio=float(
                os.getenv("ARGUS_DOCUMENT_ADMISSION_MEMORY_RATIO", "0.70")
            ),
            document_upload_root=os.getenv(
                "ARGUS_DOCUMENT_UPLOAD_ROOT", "data/uploads"
            ),
            redis_url=os.getenv("ARGUS_REDIS_URL") or None,
            kafka_bootstrap_servers=(
                os.getenv("ARGUS_KAFKA_BOOTSTRAP_SERVERS") or None
            ),
            kafka_client_id=os.getenv("ARGUS_KAFKA_CLIENT_ID", "argus"),
            kafka_security_protocol=os.getenv(
                "ARGUS_KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"
            ),
            kafka_sasl_mechanism=os.getenv("ARGUS_KAFKA_SASL_MECHANISM") or None,
            kafka_consumer_group=os.getenv(
                "ARGUS_KAFKA_CONSUMER_GROUP", "argus-audit-metrics-v1"
            ),
            kafka_consumer_max_attempts=int(
                os.getenv("ARGUS_KAFKA_CONSUMER_MAX_ATTEMPTS", "3")
            ),
            kafka_consumer_retry_backoff_ms=int(
                os.getenv("ARGUS_KAFKA_CONSUMER_RETRY_BACKOFF_MS", "100")
            ),
            kafka_consumer_poll_timeout_ms=int(
                os.getenv("ARGUS_KAFKA_CONSUMER_POLL_TIMEOUT_MS", "1000")
            ),
            kafka_consumer_stale_after_seconds=int(
                os.getenv("ARGUS_KAFKA_CONSUMER_STALE_AFTER_SECONDS", "15")
            ),
            kafka_audit_retention_count=int(
                os.getenv("ARGUS_KAFKA_AUDIT_RETENTION_COUNT", "5000")
            ),
            kafka_audit_retention_days=int(
                os.getenv("ARGUS_KAFKA_AUDIT_RETENTION_DAYS", "30")
            ),
            event_consumer_health_file=os.getenv(
                "ARGUS_EVENT_CONSUMER_HEALTH_FILE",
                "/tmp/argus-event-consumer.live",
            ),
            s3_bucket=os.getenv("ARGUS_S3_BUCKET") or None,
            s3_prefix=os.getenv("ARGUS_S3_PREFIX", "argus").strip("/"),
            aws_region=os.getenv("AWS_REGION", "us-west-2"),
            otel_exporter_otlp_endpoint=(
                os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None
            ),
        )


def get_settings() -> Settings:
    return Settings.from_env()
