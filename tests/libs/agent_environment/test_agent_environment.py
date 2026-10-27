"""Tests for building the Claude Agent SDK subprocess environment from Settings."""

import pytest

from candidate_match_agent.libs.agent_environment.agent_environment import get_agent_environment
from candidate_match_agent.libs.settings import Provider, Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_portkey_without_virtual_key_sends_only_the_api_key_header():
    settings = _settings(provider=Provider.PORTKEY, portkey_api_key="pk-secret")

    env = get_agent_environment(settings).env

    assert env == {
        "ANTHROPIC_BASE_URL": settings.portkey_base_url,
        "ANTHROPIC_API_KEY": "pk-secret",
        "ANTHROPIC_CUSTOM_HEADERS": "x-portkey-api-key: pk-secret",
    }


def test_portkey_with_virtual_key_appends_the_virtual_key_header():
    settings = _settings(
        provider=Provider.PORTKEY, portkey_api_key="pk-secret", portkey_virtual_key="aws-bedrock-use2"
    )

    env = get_agent_environment(settings).env

    assert env["ANTHROPIC_CUSTOM_HEADERS"] == (
        "x-portkey-api-key: pk-secret\nx-portkey-virtual-key: aws-bedrock-use2"
    )


def test_anthropic_provider_has_no_custom_headers():
    settings = _settings(provider=Provider.ANTHROPIC, anthropic_api_key="an-secret")

    env = get_agent_environment(settings).env

    assert env == {
        "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
        "ANTHROPIC_API_KEY": "an-secret",
    }


@pytest.mark.parametrize("provider", [Provider.PORTKEY, Provider.ANTHROPIC])
def test_raises_when_the_provider_s_api_key_is_missing(provider: Provider):
    settings = _settings(provider=provider)

    with pytest.raises(ValueError, match=f"{provider.value.upper()}_API_KEY"):
        get_agent_environment(settings)


@pytest.mark.parametrize("provider", [Provider.PORTKEY, Provider.ANTHROPIC])
def test_disable_prompt_caching_adds_the_env_var(provider: Provider):
    settings = _settings(
        provider=provider,
        portkey_api_key="pk-secret",
        anthropic_api_key="an-secret",
        disable_prompt_caching=True,
    )

    env = get_agent_environment(settings).env

    assert env["DISABLE_PROMPT_CACHING"] == "1"


def test_prompt_caching_env_var_is_absent_by_default():
    settings = _settings(provider=Provider.PORTKEY, portkey_api_key="pk-secret")

    env = get_agent_environment(settings).env

    assert "DISABLE_PROMPT_CACHING" not in env
