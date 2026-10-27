"""Shared fixtures for tests of libs/settings.py and libs/logger.py."""

import pytest

from candidate_match_agent.libs.settings import get_settings

_SETTINGS_ENV_KEYS = [
    "CANDIDATE_MATCH_AGENT_PROVIDER",
    "CANDIDATE_MATCH_AGENT_LOG_LEVEL",
    "CANDIDATE_MATCH_AGENT_PORTKEY_BASE_URL",
    "CANDIDATE_MATCH_AGENT_PORTKEY_API_KEY",
    "CANDIDATE_MATCH_AGENT_ANTHROPIC_BASE_URL",
    "CANDIDATE_MATCH_AGENT_ANTHROPIC_API_KEY",
]


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Make Settings()/get_settings() deterministic in tests.

    Clears ambient CANDIDATE_MATCH_AGENT_* env vars (a developer's shell or the
    real .env file could otherwise leak into assertions) and resets the
    get_settings() cache so each test starts from a clean singleton.
    """
    for key in _SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
