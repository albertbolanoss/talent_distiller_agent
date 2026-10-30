"""Redis-backed store for parallel MCP resume and job posting extraction state."""

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import redis.asyncio as redis
from labs_agent_lib import get_logger
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger(__name__)
MODULE = "[RedisJobStore]"

AGENT_JSON_ADAPTER = TypeAdapter(dict[str, Any] | list[Any])
DESIRABLE_PREFIX = "desirable_"


class DocumentType(StrEnum):
    """Supported document pipelines."""

    RESUME = "resume"
    JOB_POSTING = "job_posting"


class ExtractionField(StrEnum):
    """Mandatory MCP extraction domains (shared by Resume and Job Posting)."""

    TECHNICAL_SKILLS = "technical_skills"
    SOFT_SKILLS = "soft_skills"
    CERTIFICATIONS = "certifications"
    LANGUAGES = "languages"


class DesirableExtractionField(StrEnum):
    """Desirable MCP extraction domains (exclusive to Job Posting)."""

    TECHNICAL_SKILLS = f"{DESIRABLE_PREFIX}{ExtractionField.TECHNICAL_SKILLS}"
    SOFT_SKILLS = f"{DESIRABLE_PREFIX}{ExtractionField.SOFT_SKILLS}"
    CERTIFICATIONS = f"{DESIRABLE_PREFIX}{ExtractionField.CERTIFICATIONS}"
    LANGUAGES = f"{DESIRABLE_PREFIX}{ExtractionField.LANGUAGES}"


class JobRedisField(StrEnum):
    """Internal control fields stored in the Redis hash."""

    FILE_NAME = "file_name"
    RESUME_PATH = "resume_path"
    CONTENT = "content"
    SESSION_ID = "session_id"
    COMPLETED = "completed"
    REVISION_NUMBER = "revision_number"


class RedisSettings(BaseSettings):
    """Connection settings for the extraction job store."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CANDIDATE_MATCH_AGENT_REDIS_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "localhost"
    password: SecretStr = SecretStr("")
    db: int = 0


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Return the cached Redis connection settings singleton."""
    return RedisSettings()


@dataclass(frozen=True, slots=True)
class JobStatus:
    """Immutable snapshot of a job's current checkpoint state in Redis."""

    resume_path: str
    revision_number: int
    has_content: bool
    missing_fields: list[str]
    session_id: str | None = None

    @property
    def is_completed(self) -> bool:
        return self.has_content and not self.missing_fields


class UnifiedResumeJob(BaseModel):
    """Unified final output for a Resume (or base mandatory fields)."""

    model_config = ConfigDict(extra="ignore")

    file_name: str
    resume_path: str
    session_id: str | None = None
    is_completed: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_completed", JobRedisField.COMPLETED),
    )
    revision_number: int = 0
    content: str | None = None
    technical_skills: dict[str, Any] | list[Any] | None = None
    soft_skills: dict[str, Any] | list[Any] | None = None
    certifications: dict[str, Any] | list[Any] | None = None
    languages: dict[str, Any] | list[Any] | None = None
    errors: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        ExtractionField.TECHNICAL_SKILLS,
        ExtractionField.SOFT_SKILLS,
        ExtractionField.CERTIFICATIONS,
        ExtractionField.LANGUAGES,
        mode="before",
    )
    @classmethod
    def _parse_redis_json(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip():
            return AGENT_JSON_ADAPTER.validate_json(value)
        return value or None


class UnifiedJobPostingJob(UnifiedResumeJob):
    """Unified final output for a Job Posting (mandatory + desirable fields)."""

    desirable_technical_skills: dict[str, Any] | list[Any] | None = None
    desirable_soft_skills: dict[str, Any] | list[Any] | None = None
    desirable_certifications: dict[str, Any] | list[Any] | None = None
    desirable_languages: dict[str, Any] | list[Any] | None = None

    @field_validator(
        DesirableExtractionField.TECHNICAL_SKILLS,
        DesirableExtractionField.SOFT_SKILLS,
        DesirableExtractionField.CERTIFICATIONS,
        DesirableExtractionField.LANGUAGES,
        mode="before",
    )
    @classmethod
    def _parse_desirable_redis_json(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip():
            return AGENT_JSON_ADAPTER.validate_json(value)
        return value or None


@dataclass(frozen=True, slots=True)
class DocumentStorageSpec:
    """Storage configuration per document type."""

    doc_type: DocumentType
    key_prefix: str
    extraction_fields: tuple[str, ...]
    model_cls: type[UnifiedResumeJob]


STORAGE_SPECS: dict[DocumentType, DocumentStorageSpec] = {
    DocumentType.RESUME: DocumentStorageSpec(
        doc_type=DocumentType.RESUME,
        key_prefix="resume_job:",
        extraction_fields=tuple(f.value for f in ExtractionField),
        model_cls=UnifiedResumeJob,
    ),
    DocumentType.JOB_POSTING: DocumentStorageSpec(
        doc_type=DocumentType.JOB_POSTING,
        key_prefix="job_posting:",
        extraction_fields=(
            *(f.value for f in ExtractionField),
            *(f.value for f in DesirableExtractionField),
        ),
        model_cls=UnifiedJobPostingJob,
    ),
}


class RedisJobStore:
    """State store for checkpointing resume and job posting extraction jobs in Redis."""

    ERROR_FIELD_PREFIX = "error:"

    def __init__(
        self,
        doc_type: DocumentType = DocumentType.RESUME,
        settings: RedisSettings | None = None,
        client: redis.Redis | None = None,
        ttl_seconds: int = 86400,
    ) -> None:
        self.doc_type = doc_type
        self.spec = STORAGE_SPECS[doc_type]
        self.settings = settings or get_redis_settings()
        self.ttl = ttl_seconds
        self.redis = client or redis.Redis(
            host=self.settings.host,
            password=self.settings.password.get_secret_value() or None,
            db=self.settings.db,
            decode_responses=True,
        )

    @property
    def extraction_fields(self) -> tuple[str, ...]:
        return self.spec.extraction_fields

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    def get_job_key(self, file_path: str) -> str:
        """Builds a deterministic Redis key using the document type prefix and normalized file name."""
        file_name = Path(file_path).name.lower().strip()
        return f"{self.spec.key_prefix}{file_name}"

    def get_target_fields_for_base_field(self, base_field: str) -> tuple[str, ...]:
        """Returns the Redis field(s) associated with a base MCP extraction domain."""
        if self.doc_type == DocumentType.JOB_POSTING:
            return (base_field, f"{DESIRABLE_PREFIX}{base_field}")
        return (base_field,)

    async def init_or_get_state(self, file_path: str) -> dict[str, str]:
        """Initializes the job hash in Redis if new, or returns existing raw state."""
        key = self.get_job_key(file_path)
        state = await self.redis.hgetall(key)

        if not state:
            initial_data: dict[str, str] = {
                JobRedisField.FILE_NAME: Path(file_path).name,
                JobRedisField.RESUME_PATH: file_path,
                JobRedisField.COMPLETED: self._encode_bool(False),
                JobRedisField.REVISION_NUMBER: "0",
            }
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.hset(key, mapping=initial_data)
                pipe.expire(key, self.ttl)
                await pipe.execute()
            return initial_data

        return state

    async def get_status(self, file_path: str) -> JobStatus:
        """Returns a typed snapshot of the job's current state without mutating it."""
        state = await self.init_or_get_state(file_path)
        return JobStatus(
            resume_path=file_path,
            revision_number=int(state.get(JobRedisField.REVISION_NUMBER, 0)),
            has_content=bool(state.get(JobRedisField.CONTENT)),
            missing_fields=[f for f in self.extraction_fields if not state.get(f)],
            session_id=state.get(JobRedisField.SESSION_ID),
        )

    async def increment_attempts(self, file_path: str) -> int:
        """Atomically increments and returns the revision number in Redis."""
        await self.init_or_get_state(file_path)
        key = self.get_job_key(file_path)
        attempts = await self.redis.hincrby(key, JobRedisField.REVISION_NUMBER, 1)
        logger.debug("%s Attempt #%d for key=%s", MODULE, attempts, key)
        return int(attempts)

    async def save_content(self, file_path: str, content: str) -> None:
        """Checkpoints the extracted document raw text and clears any prior read error."""
        key = self.get_job_key(file_path)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, JobRedisField.CONTENT, content)
            pipe.hdel(key, f"{self.ERROR_FIELD_PREFIX}{JobRedisField.CONTENT}")
            await pipe.execute()
        logger.debug("%s Saved document content in Redis key=%s", MODULE, key)

    async def save_agent_result(self, file_path: str, field: str, raw_json: str) -> None:
        """Validates that raw_json is a valid JSON object/array before checkpointing in Redis."""
        key = self.get_job_key(file_path)
        try:
            validated_data = AGENT_JSON_ADAPTER.validate_json(raw_json)
            serialized = AGENT_JSON_ADAPTER.dump_json(validated_data).decode("utf-8")
        except ValidationError as exc:
            logger.warning(
                "%s Invalid JSON for field=%s | key=%s: %s",
                MODULE,
                field,
                key,
                exc,
            )
            await self.save_agent_error(file_path, field, f"Invalid JSON output: {raw_json}")
            return

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, field, serialized)
            pipe.hdel(key, f"{self.ERROR_FIELD_PREFIX}{field}")
            await pipe.execute()
        logger.info("%s Checkpointed agent field=%s for key=%s", MODULE, field, key)

    async def save_agent_error(self, file_path: str, field: str, error_msg: str) -> None:
        """Records a failed MCP tool call for observability and retry tracking."""
        key = self.get_job_key(file_path)
        await self.redis.hset(key, f"{self.ERROR_FIELD_PREFIX}{field}", error_msg)
        logger.warning("%s Recorded error for field=%s | key=%s", MODULE, field, key)

    async def save_session_and_completion(
        self,
        file_path: str,
        is_completed: bool,
        session_id: str | None = None,
    ) -> None:
        """Persists the completion flag and optional session_id in Redis."""
        key = self.get_job_key(file_path)
        updates: dict[str, str] = {JobRedisField.COMPLETED: self._encode_bool(is_completed)}
        if session_id:
            updates[JobRedisField.SESSION_ID] = session_id
        await self.redis.hset(key, mapping=updates)

    async def unify_by_filename(self, file_path_or_name: str) -> UnifiedResumeJob:
        """Reconstructs and validates the unified Pydantic model directly from Redis."""
        key = self.get_job_key(file_path_or_name)
        state = await self.redis.hgetall(key)
        if not state:
            raise KeyError(f"No job found in Redis for key={key}")

        errors = {
            k.removeprefix(self.ERROR_FIELD_PREFIX): v
            for k, v in state.items()
            if k.startswith(self.ERROR_FIELD_PREFIX)
        }

        payload: dict[str, Any] = {
            JobRedisField.FILE_NAME: Path(file_path_or_name).name,
            JobRedisField.RESUME_PATH: file_path_or_name,
            **state,
            "errors": errors,
        }
        return self.spec.model_cls.model_validate(payload)

    async def close(self) -> None:
        """Closes the underlying Redis connection."""
        await self.redis.aclose()

    @staticmethod
    def _encode_bool(value: bool) -> str:
        return "1" if value else "0"
