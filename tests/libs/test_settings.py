import pytest

from candidate_match_agent.libs.settings import LogLevel, Provider, Settings, get_settings


def test_provider_values():
    assert Provider.PORTKEY == "portkey"
    assert Provider.ANTHROPIC == "anthropic"


def test_log_level_values():
    assert LogLevel.DEBUG == "DEBUG"
    assert LogLevel.INFO == "INFO"
    assert LogLevel.WARNING == "WARNING"
    assert LogLevel.ERROR == "ERROR"


def test_defaults_when_no_env_vars_are_set():
    settings = Settings(_env_file=None)

    assert settings.provider is Provider.PORTKEY
    assert settings.log_level is LogLevel.INFO
    assert settings.portkey_base_url == "https://portkeygateway.perficient.com"
    assert settings.anthropic_base_url == "https://api.anthropic.com"
    assert settings.portkey_api_key.get_secret_value() == ""
    assert settings.anthropic_api_key.get_secret_value() == ""


def test_reads_provider_and_log_level_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.provider is Provider.ANTHROPIC
    assert settings.log_level is LogLevel.DEBUG


def test_reads_base_urls_and_api_keys_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PORTKEY_BASE_URL", "https://portkey.example.com")
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PORTKEY_API_KEY", "portkey-secret")
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_ANTHROPIC_BASE_URL", "https://anthropic.example.com")
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_ANTHROPIC_API_KEY", "anthropic-secret")

    settings = Settings(_env_file=None)

    assert settings.portkey_base_url == "https://portkey.example.com"
    assert settings.portkey_api_key.get_secret_value() == "portkey-secret"
    assert settings.anthropic_base_url == "https://anthropic.example.com"
    assert settings.anthropic_api_key.get_secret_value() == "anthropic-secret"


def test_api_keys_are_masked_in_str_and_repr(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PORTKEY_API_KEY", "super-secret")

    settings = Settings(_env_file=None)

    assert "super-secret" not in str(settings.portkey_api_key)
    assert "super-secret" not in repr(settings)


def test_unknown_env_vars_with_the_app_prefix_are_ignored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_SOME_UNKNOWN_FIELD", "whatever")

    settings = Settings(_env_file=None)  # must not raise

    assert settings.provider is Provider.PORTKEY


def test_get_settings_returns_a_settings_instance(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PROVIDER", "anthropic")

    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.provider is Provider.ANTHROPIC


def test_get_settings_is_cached_across_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PROVIDER", "anthropic")
    first = get_settings()

    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_PROVIDER", "portkey")
    second = get_settings()

    assert first is second
    assert second.provider is Provider.ANTHROPIC
