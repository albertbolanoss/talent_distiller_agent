"""Tests for the Redis-backed resume/job-posting extraction job store."""

import fakeredis
import pytest
from fakeredis import aioredis as fake_redis

from talent_distiller_agent.settings import Settings, get_settings
from talent_distiller_agent.storage.redis_job_store import (
    DESIRABLE_PREFIX,
    DocumentType,
    RedisJobStore,
    UnifiedJobPostingJob,
    UnifiedResumeJob,
)

RESUME_PATH = "resume/Jane Doe.pdf"
JOB_POSTING_PATH = "job_posting/Backend Engineer.pdf"


def _store(doc_type: DocumentType = DocumentType.RESUME) -> RedisJobStore:
    server = fakeredis.FakeServer()
    return RedisJobStore(
        doc_type=doc_type, client=fake_redis.FakeRedis(server=server, decode_responses=True)
    )


def test_get_job_key_normalizes_the_file_name_for_a_resume():
    store = _store()
    assert store.get_job_key("Resume/Folder/Jane Doe.PDF ") == "resume_job:jane doe.pdf"


def test_get_job_key_uses_the_job_posting_prefix():
    store = _store(DocumentType.JOB_POSTING)
    assert store.get_job_key("Job Posting/Backend Engineer.PDF") == "job_posting:backend engineer.pdf"


def test_extraction_fields_are_mandatory_only_for_a_resume():
    store = _store()
    assert store.extraction_fields == (
        "technical_skills",
        "soft_skills",
        "certifications",
        "languages",
    )


def test_extraction_fields_include_desirable_fields_for_a_job_posting():
    store = _store(DocumentType.JOB_POSTING)
    assert store.extraction_fields == (
        "technical_skills",
        "soft_skills",
        "certifications",
        "languages",
        "desirable_technical_skills",
        "desirable_soft_skills",
        "desirable_certifications",
        "desirable_languages",
    )


def test_get_target_fields_for_base_field_returns_only_the_base_field_for_a_resume():
    store = _store()
    assert store.get_target_fields_for_base_field("languages") == ("languages",)


def test_get_target_fields_for_base_field_includes_the_desirable_field_for_a_job_posting():
    store = _store(DocumentType.JOB_POSTING)
    assert store.get_target_fields_for_base_field("languages") == (
        "languages",
        f"{DESIRABLE_PREFIX}languages",
    )


async def test_init_or_get_state_creates_a_new_job_on_first_call():
    store = _store()

    state = await store.init_or_get_state(RESUME_PATH)

    assert state == {
        "file_name": "Jane Doe.pdf",
        "file_path": RESUME_PATH,
        "completed": "0",
        "revision_number": "0",
    }
    ttl = await store.redis.ttl(store.get_job_key(RESUME_PATH))
    assert ttl > 0


async def test_init_or_get_state_returns_existing_state_without_resetting_it():
    store = _store()
    await store.init_or_get_state(RESUME_PATH)
    await store.save_content(RESUME_PATH, "already here")

    state = await store.init_or_get_state(RESUME_PATH)

    assert state["content"] == "already here"


async def test_save_content_checkpoints_the_raw_text():
    store = _store()

    await store.save_content(RESUME_PATH, "raw text")

    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert state["content"] == "raw text"


async def test_save_agent_result_serializes_valid_json_and_clears_prior_error():
    store = _store()
    await store.save_agent_error(RESUME_PATH, "technical_skills", "boom")

    await store.save_agent_result(RESUME_PATH, "technical_skills", '{"skills": ["python"]}')

    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert state["technical_skills"] == '{"skills":["python"]}'
    assert "error:technical_skills" not in state


async def test_save_agent_result_records_invalid_json_as_an_agent_error():
    store = _store()

    await store.save_agent_result(RESUME_PATH, "soft_skills", "not json")

    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert "soft_skills" not in state
    assert state["error:soft_skills"] == "Invalid JSON output: not json"


async def test_save_agent_error_records_the_error_message():
    store = _store()

    await store.save_agent_error(RESUME_PATH, "languages", "timeout")

    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert state["error:languages"] == "timeout"


async def test_increment_attempts_counts_up_atomically_per_job():
    store = _store()

    first = await store.increment_attempts(RESUME_PATH)
    second = await store.increment_attempts(RESUME_PATH)

    assert (first, second) == (1, 2)
    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert state["revision_number"] == "2"


async def test_get_status_reports_completed_when_content_and_all_fields_present():
    store = _store()
    await store.save_content(RESUME_PATH, "text")
    for field in store.extraction_fields:
        await store.save_agent_result(RESUME_PATH, field, "{}")

    status = await store.get_status(RESUME_PATH)

    assert status.is_completed is True
    assert status.has_content is True
    assert status.missing_fields == []


async def test_get_status_reports_incomplete_when_fields_are_missing():
    store = _store()
    await store.save_content(RESUME_PATH, "text")

    status = await store.get_status(RESUME_PATH)

    assert status.is_completed is False
    assert status.has_content is True
    assert status.missing_fields == list(store.extraction_fields)


async def test_get_status_reports_incomplete_for_a_job_posting_missing_only_desirable_fields():
    store = _store(DocumentType.JOB_POSTING)
    await store.save_content(JOB_POSTING_PATH, "text")
    for field in ("technical_skills", "soft_skills", "certifications", "languages"):
        await store.save_agent_result(JOB_POSTING_PATH, field, "{}")

    status = await store.get_status(JOB_POSTING_PATH)

    assert status.is_completed is False
    assert status.missing_fields == [
        "desirable_technical_skills",
        "desirable_soft_skills",
        "desirable_certifications",
        "desirable_languages",
    ]


async def test_save_session_and_completion_persists_the_flag_and_session_id():
    store = _store()

    await store.save_session_and_completion(RESUME_PATH, is_completed=True, session_id="session-1")

    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert state["session_id"] == "session-1"
    assert state["completed"] == "1"


async def test_save_session_and_completion_without_a_session_id_does_not_set_it():
    store = _store()

    await store.save_session_and_completion(RESUME_PATH, is_completed=False)

    state = await store.redis.hgetall(store.get_job_key(RESUME_PATH))
    assert "session_id" not in state
    assert state["completed"] == "0"


async def test_get_status_reports_has_content_false_for_a_brand_new_job():
    store = _store()

    status = await store.get_status(RESUME_PATH)

    assert status.has_content is False
    assert status.missing_fields == list(store.extraction_fields)


async def test_get_status_reports_has_content_true_once_content_is_saved():
    store = _store()
    await store.init_or_get_state(RESUME_PATH)
    await store.save_content(RESUME_PATH, "text")

    status = await store.get_status(RESUME_PATH)

    assert status.has_content is True
    assert status.missing_fields == list(store.extraction_fields)


async def test_unify_by_filename_raises_when_no_job_exists():
    store = _store()

    with pytest.raises(KeyError):
        await store.unify_by_filename(RESUME_PATH)


async def test_unify_by_filename_combines_content_fields_and_errors():
    store = _store()
    await store.save_content(RESUME_PATH, "raw text")
    await store.save_agent_result(RESUME_PATH, "technical_skills", '{"skills": ["python"]}')
    await store.save_agent_error(RESUME_PATH, "languages", "timeout")
    await store.save_session_and_completion(RESUME_PATH, is_completed=False, session_id="session-99")

    job = await store.unify_by_filename(RESUME_PATH)

    assert job == UnifiedResumeJob(
        file_name="Jane Doe.pdf",
        file_path=RESUME_PATH,
        session_id="session-99",
        is_completed=False,
        content="raw text",
        technical_skills={"skills": ["python"]},
        soft_skills=None,
        certifications=None,
        languages=None,
        errors={"languages": "timeout"},
    )


async def test_unify_by_filename_returns_a_unified_job_posting_job_with_desirable_fields():
    store = _store(DocumentType.JOB_POSTING)
    await store.save_content(JOB_POSTING_PATH, "raw text")
    await store.save_agent_result(JOB_POSTING_PATH, "technical_skills", '{"skills": ["python"]}')
    await store.save_agent_result(
        JOB_POSTING_PATH, "desirable_technical_skills", '{"skills": ["rust"]}'
    )

    job = await store.unify_by_filename(JOB_POSTING_PATH)

    assert isinstance(job, UnifiedJobPostingJob)
    assert job == UnifiedJobPostingJob(
        file_name="Backend Engineer.pdf",
        file_path=JOB_POSTING_PATH,
        content="raw text",
        technical_skills={"skills": ["python"]},
        soft_skills=None,
        certifications=None,
        languages=None,
        desirable_technical_skills={"skills": ["rust"]},
        desirable_soft_skills=None,
        desirable_certifications=None,
        desirable_languages=None,
    )


async def test_close_closes_the_underlying_connection():
    store = _store()

    await store.close()


async def test_async_context_manager_closes_the_connection_on_exit():
    server = fakeredis.FakeServer()
    store = RedisJobStore(client=fake_redis.FakeRedis(server=server, decode_responses=True))

    async with store as entered:
        assert entered is store
        await entered.save_content(RESUME_PATH, "text")


def test_redis_job_store_builds_a_client_from_settings_when_none_injected():
    settings = Settings(
        _env_file=None, redis_host="redis.internal", redis_password="secret", redis_db=2
    )

    store = RedisJobStore(settings=settings)

    kwargs = store.redis.connection_pool.connection_kwargs
    assert kwargs["host"] == "redis.internal"
    assert kwargs["password"] == "secret"
    assert kwargs["db"] == 2


def test_redis_job_store_uses_cached_settings_when_none_given():
    get_settings.cache_clear()

    store = RedisJobStore()

    assert store.redis.connection_pool.connection_kwargs["host"] == get_settings().redis_host
    get_settings.cache_clear()
