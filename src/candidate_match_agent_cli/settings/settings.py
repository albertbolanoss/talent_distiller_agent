from functools import lru_cache
from pydantic import model_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CANDIDATE_MATCH_AGENT_",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Resume settings
    resume_dir: str = "resume"
    resume_poll_interval_seconds: float = 10.0
    resume_max_files_per_batch: int = 3
    coordinator_processed_folder: str | None = None
    coordinator_failed_folder: str | None = None

    # Job Posting settings
    job_posting_dir: str = "job_posting"
    job_posting_poll_interval_seconds: float = 10.0
    job_posting_max_files_per_batch: int = 3
    job_posting_processed_folder: str | None = None
    job_posting_failed_folder: str | None = None

    # Shared MCP & Coordinator settings
    skill_agent_mcp_url: str = "http://127.0.0.1:8000/mcp"
    coordinator_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    coordinator_max_revision_number: int = 3

    # Redis 
    redis_host: str = "localhost"
    redis_password: SecretStr = SecretStr("")
    redis_db: int = 0

    @model_validator(mode="after")
    def _resolve_default_folders(self) -> "Settings":
        if not self.coordinator_processed_folder:
            self.coordinator_processed_folder = f"{self.resume_dir}/processed"
        if not self.coordinator_failed_folder:
            self.coordinator_failed_folder = f"{self.resume_dir}/failed"
        if not self.job_posting_processed_folder:
            self.job_posting_processed_folder = f"{self.job_posting_dir}/processed"
        if not self.job_posting_failed_folder:
            self.job_posting_failed_folder = f"{self.job_posting_dir}/failed"
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
