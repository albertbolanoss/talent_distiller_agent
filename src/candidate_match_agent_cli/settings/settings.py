from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CANDIDATE_MATCH_AGENT_",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    resume_dir: str = "resume"
    resume_poll_interval_seconds: float = 300
    resume_max_files_per_batch: int = 3

    coordinator_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    coordinator_processed_folder: str = f"{resume_dir}/processed"
    coordinator_failed_folder: str = f"{resume_dir}/failed"
    coordinator_max_revision_number: int = 3


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
