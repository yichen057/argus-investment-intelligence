from investment_agent.config import Settings
import pytest


def test_settings_defaults_keep_external_integrations_off(monkeypatch) -> None:
    monkeypatch.delenv("ARGUS_ENABLE_CLOUD_SERVICES", raising=False)
    monkeypatch.delenv("ARGUS_ENABLE_GMAIL", raising=False)
    monkeypatch.delenv("ARGUS_ENABLE_ROBINHOOD", raising=False)
    monkeypatch.delenv("ARGUS_ENABLE_EXTERNAL_MARKET_DATA", raising=False)
    monkeypatch.delenv("ARGUS_ENABLE_MARKET_HEATMAP", raising=False)
    monkeypatch.delenv("ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE", raising=False)
    monkeypatch.delenv("ARGUS_MARKET_DATA_PROVIDER", raising=False)

    settings = Settings.from_env()

    assert settings.default_model_selection_mode == "auto"
    assert not settings.enable_cloud_services
    assert not settings.enable_gmail
    assert not settings.enable_robinhood
    assert not settings.enable_external_market_data
    assert not settings.enable_market_heatmap
    assert not settings.enable_unified_etf_universe
    assert settings.market_data_provider_code == "01"
    assert settings.market_data_provider_key == "robinhood"


def test_settings_reads_local_dev_overrides(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_ENV", "test")
    monkeypatch.setenv("ARGUS_API_PORT", "9000")
    monkeypatch.setenv("ARGUS_API_RELOAD", "true")
    monkeypatch.setenv(
        "ARGUS_CORS_ORIGINS",
        "http://localhost:5173, http://127.0.0.1:5173",
    )
    monkeypatch.setenv("ARGUS_SELF_HOSTED_MODEL_BASE_URL", "http://localhost:8001")
    monkeypatch.setenv("ARGUS_SELF_HOSTED_MODEL_NAME", "tiny-local-model")
    monkeypatch.setenv("ARGUS_TOOL_TIMEOUT_MS", "2500")
    monkeypatch.setenv("ARGUS_TOOL_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("ARGUS_TOOL_RETRY_BACKOFF_MS", "25")
    monkeypatch.setenv("ARGUS_MODEL_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ARGUS_MODEL_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("ARGUS_MODEL_RETRY_BACKOFF_MS", "150")
    monkeypatch.setenv("ARGUS_MARKET_ANALYSIS_TIMEOUT_MS", "45000")
    monkeypatch.setenv("ARGUS_MARKET_ANALYSIS_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("ARGUS_MARKET_ANALYSIS_MAX_OUTPUT_TOKENS", "1500")
    monkeypatch.setenv("ARGUS_MARKET_ANALYSIS_TRACE_RETENTION_COUNT", "12")
    monkeypatch.setenv("ARGUS_MARKET_ANALYSIS_TRACE_RETENTION_DAYS", "7")
    monkeypatch.setenv("ARGUS_ETF_SELECTION_ENGINE", "model")
    monkeypatch.setenv("ARGUS_DEEPSEEK_API_KEY", "deepseek-test")
    monkeypatch.setenv("ARGUS_KIMI_API_KEY", "kimi-test")
    monkeypatch.setenv("ARGUS_KIMI_TIMEOUT_MS", "45000")
    monkeypatch.setenv("ARGUS_EXA_API_KEY", "exa-test")
    monkeypatch.setenv("ARGUS_EXA_SEARCH_TYPE", "fast")
    monkeypatch.setenv("ARGUS_EXA_MAX_RESULTS", "4")
    monkeypatch.setenv("ARGUS_WEB_SEARCH_MAX_CALLS", "1")
    monkeypatch.setenv("ARGUS_ENABLE_EXTERNAL_MARKET_DATA", "true")
    monkeypatch.setenv("ARGUS_ENABLE_MARKET_HEATMAP", "true")
    monkeypatch.setenv("ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE", "true")
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER", "02")

    settings = Settings.from_env()

    assert settings.env == "test"
    assert settings.api_port == 9000
    assert settings.api_reload
    assert settings.cors_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert settings.self_hosted_model_base_url == "http://localhost:8001"
    assert settings.self_hosted_model_name == "tiny-local-model"
    assert settings.tool_timeout_ms == 2500
    assert settings.tool_max_attempts == 4
    assert settings.tool_retry_backoff_ms == 25
    assert settings.model_timeout_ms == 30000
    assert settings.model_max_attempts == 5
    assert settings.model_retry_backoff_ms == 150
    assert settings.market_analysis_timeout_ms == 45000
    assert settings.market_analysis_max_attempts == 1
    assert settings.market_analysis_max_output_tokens == 1500
    assert settings.market_analysis_trace_retention_count == 12
    assert settings.market_analysis_trace_retention_days == 7
    assert settings.etf_selection_engine == "model"
    assert settings.deepseek_api_key == "deepseek-test"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.deepseek_input_cost_per_million == 0.14
    assert settings.kimi_api_key == "kimi-test"
    assert settings.kimi_model == "kimi-k2.6"
    assert settings.kimi_timeout_ms == 45000
    assert settings.kimi_output_cost_per_million == 4.0
    assert settings.exa_api_key == "exa-test"
    assert settings.exa_search_type == "fast"
    assert settings.exa_max_results == 4
    assert settings.web_search_max_calls == 1
    assert settings.enable_external_market_data
    assert settings.enable_market_heatmap
    assert settings.enable_unified_etf_universe
    assert settings.market_data_provider_code == "02"
    assert settings.market_data_provider_key == "twelve_data"
    assert settings.market_data_provider_name == "Twelve Data"


def test_settings_rejects_unknown_etf_selection_engine(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_ETF_SELECTION_ENGINE", "silent-auto-fallback")

    with pytest.raises(ValueError, match="deterministic, model"):
        Settings.from_env()


def test_settings_rejects_unknown_market_data_provider(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER", "09")

    with pytest.raises(ValueError, match="market-data provider code"):
        Settings.from_env()
