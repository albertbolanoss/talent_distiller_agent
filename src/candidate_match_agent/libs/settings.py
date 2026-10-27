from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    """Anthropic-Messages-API-compatible gateways this agent can route through."""

    PORTKEY = "portkey"
    ANTHROPIC = "anthropic"


class LogLevel(StrEnum):
    """Verbosity for labs_resume_agent.libs.logger - maps 1:1 to stdlib logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CANDIDATE_MATCH_AGENT_",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    provider: Provider = Provider.PORTKEY
    log_level: LogLevel = LogLevel.INFO

    portkey_base_url: str = "https://portkeygateway.perficient.com"
    portkey_api_key: SecretStr = SecretStr("")
    portkey_virtual_key: str = ""

    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: SecretStr = SecretStr("")

    resume_dir: str = "resume"
    resume_poll_interval_seconds: float = 300
    resume_max_files_per_batch: int = 3

    disable_prompt_caching: bool = False
    """Disables Anthropic prompt caching (no `cache_control` breakpoints) for the agent's requests.
    Enable during development (CANDIDATE_MATCH_AGENT_DISABLE_PROMPT_CACHING=true) when iterating on the
    system prompt, since a cached prefix can otherwise be reused across runs within the cache's TTL."""


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
