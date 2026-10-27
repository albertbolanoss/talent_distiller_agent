"""Builds the Claude Agent SDK environment for the gateway configured in Settings."""

from dataclasses import dataclass

from candidate_match_agent.libs.settings import Provider, Settings


@dataclass(frozen=True, slots=True)
class AgentEnvironment:
    """What ClaudeAgentOptions needs to reach a model gateway.

    Attributes:
        env: Environment overrides for ClaudeAgentOptions.env; the SDK merges this
            over the inherited environment before spawning the `claude` subprocess.
            The model itself is set in code, not here.
    """

    env: dict[str, str]


def get_agent_environment(settings: Settings) -> AgentEnvironment:
    """Build the AgentEnvironment for the provider configured in settings.provider.

    Both supported providers speak the Anthropic Messages API, so routing to either
    one is just a matter of pointing ANTHROPIC_BASE_URL/ANTHROPIC_API_KEY at it.
    """
    if settings.provider is Provider.PORTKEY:
        base_url, api_key = settings.portkey_base_url, settings.portkey_api_key
    else:
        base_url, api_key = settings.anthropic_base_url, settings.anthropic_api_key

    if not api_key.get_secret_value():
        raise ValueError(
            f"CANDIDATE_MATCH_AGENT_{settings.provider.value.upper()}_API_KEY is required when provider={settings.provider}"
        )

    if settings.provider is Provider.PORTKEY:
        return AgentEnvironment(
            env={
                "ANTHROPIC_BASE_URL": base_url,
                "ANTHROPIC_API_KEY": api_key.get_secret_value(),
                "ANTHROPIC_CUSTOM_HEADERS": f"x-portkey-api-key: {api_key.get_secret_value()}",
            },
        )
    else:
        return AgentEnvironment(
            env={
                "ANTHROPIC_BASE_URL": base_url,
                "ANTHROPIC_API_KEY": api_key.get_secret_value(),
            },
        )
