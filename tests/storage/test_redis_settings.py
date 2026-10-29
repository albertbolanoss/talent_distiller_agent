"""Tests for the Redis connection settings."""

from candidate_match_agent_cli.storage import RedisSettings, get_redis_settings


def test_redis_settings_defaults_when_no_env_file():
    settings = RedisSettings(_env_file=None)

    assert settings.host == "localhost"
    assert settings.password.get_secret_value() == ""
    assert settings.db == 0


def test_get_redis_settings_is_cached():
    get_redis_settings.cache_clear()

    first = get_redis_settings()
    second = get_redis_settings()

    assert first is second
    get_redis_settings.cache_clear()
