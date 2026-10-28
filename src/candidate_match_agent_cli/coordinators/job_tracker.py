"""Redis-backed Job Tracker with password support for parallel MCP resume extraction."""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
import redis.asyncio as redis

from labs_agent_lib import get_logger

logger = get_logger(__name__)
MODULE = "[JobTracker]"

EXTRACTION_FIELDS = ("technical_skills", "soft_skills", "certifications", "languages")


class UnifiedResumeJob(BaseModel):
    """Unified final output recovered from Redis by filename."""
    file_name: str
    resume_path: str
    session_id: str | None = None
    status: str
    content: str | None = None
    technical_skills: dict[str, Any] | list[Any] | None = None
    soft_skills: dict[str, Any] | list[Any] | None = None
    certifications: dict[str, Any] | list[Any] | None = None
    languages: dict[str, Any] | list[Any] | None = None
    errors: dict[str, str] = Field(default_factory=dict)


class RedisJobTracker:
    def __init__(
        self,
        redis_url: str | None = None,
        redis_password: str | None = None,
        ttl_seconds: int = 86400,
    ) -> None:
        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        password = redis_password if redis_password is not None else os.getenv("REDIS_PASSWORD", "j1o42mBN79CJoHyba4HCIvrY")

        self.redis = redis.from_url(
            url,
            password=password,
            decode_responses=True,
        )
        self.ttl = ttl_seconds

    @staticmethod
    def get_job_key(resume_path: str) -> str:
        """Builds a deterministic Redis key using the normalized file name."""
        file_name = Path(resume_path).name.lower().strip()
        return f"resume_job:{file_name}"

    async def init_or_get_state(self, resume_path: str) -> dict[str, str]:
        """Initializes the job hash in Redis if new, or returns existing partial state."""
        key = self.get_job_key(resume_path)
        state = await self.redis.hgetall(key)
        if not state:
            initial_data = {
                "file_name": Path(resume_path).name,
                "resume_path": resume_path,
                "status": "IN_PROGRESS",
            }
            await self.redis.hset(key, mapping=initial_data)
            await self.redis.expire(key, self.ttl)
            return initial_data
        return state

    async def save_content(self, resume_path: str, content: str) -> None:
        """Checkpoints the extracted CV raw text immediately."""
        key = self.get_job_key(resume_path)
        await self.redis.hset(key, "content", content)
        logger.info("%s Saved document content in Redis key=%s", MODULE, key)

    async def save_agent_result(self, resume_path: str, field: str, raw_json: str) -> None:
        """Checkpoints an individual MCP agent's JSON result atomically."""
        key = self.get_job_key(resume_path)
        try:
            parsed = json.loads(raw_json)
            serialized = json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            serialized = json.dumps({"raw": raw_json}, ensure_ascii=False)

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, field, serialized)
            pipe.hdel(key, f"error:{field}")
            await pipe.execute()
        logger.info("%s Checkpointed agent field=%s for key=%s", MODULE, field, key)

    async def save_agent_error(self, resume_path: str, field: str, error_msg: str) -> None:
        """Records a failed MCP tool call for observability and retry tracking."""
        key = self.get_job_key(resume_path)
        await self.redis.hset(key, f"error:{field}", error_msg)
        logger.warning("%s Recorded error for field=%s | key=%s", MODULE, field, key)

    async def update_session_and_status(
        self, resume_path: str, session_id: str | None
    ) -> tuple[str, list[str]]:
        """Updates session_id, computes missing fields, and sets job status."""
        key = self.get_job_key(resume_path)
        state = await self.redis.hgetall(key)

        missing = [f for f in EXTRACTION_FIELDS if not state.get(f)]
        has_content = bool(state.get("content"))
        status = "COMPLETED" if (has_content and not missing) else "PARTIAL_FAILURE"

        updates: dict[str, str] = {"status": status}
        if session_id:
            updates["session_id"] = session_id

        await self.redis.hset(key, mapping=updates)
        return status, missing

    async def get_missing_requirements(
        self, resume_path: str
    ) -> tuple[bool, list[str], dict[str, str]]:
        """Returns `(needs_document_read, missing_agent_fields, raw_state)`."""
        state = await self.init_or_get_state(resume_path)
        needs_read = not bool(state.get("content"))
        missing_fields = [f for f in EXTRACTION_FIELDS if not state.get(f)]
        return needs_read, missing_fields, state

    async def unify_by_filename(self, resume_path_or_name: str) -> UnifiedResumeJob:
        """Looks up the job in Redis by file name, checks session_id, and unifies all partial JSONs."""
        key = self.get_job_key(resume_path_or_name)
        state = await self.redis.hgetall(key)
        if not state:
            raise KeyError(f"No job found in Redis for key={key}")

        errors = {
            k.removeprefix("error:"): v
            for k, v in state.items()
            if k.startswith("error:")
        }

        def _load_json(field_name: str) -> Any:
            val = state.get(field_name)
            return json.loads(val) if val else None

        return UnifiedResumeJob(
            file_name=state.get("file_name", Path(resume_path_or_name).name),
            resume_path=state.get("resume_path", resume_path_or_name),
            session_id=state.get("session_id"),
            status=state.get("status", "UNKNOWN"),
            content=state.get("content"),
            technical_skills=_load_json("technical_skills"),
            soft_skills=_load_json("soft_skills"),
            certifications=_load_json("certifications"),
            languages=_load_json("languages"),
            errors=errors,
        )

    async def close(self) -> None:
        await self.redis.aclose()