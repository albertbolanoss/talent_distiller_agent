"""Tests for the Redis-backed resume-extraction job store."""

import fakeredis
import pytest
from fakeredis import aioredis as fake_redis

from candidate_match_agent_cli.storage.redis_job_store import (
    RedisJobStore,
    RedisSettings,
    UnifiedResumeJob,
    get_redis_settings,
)

RESUME_PATH = "resume/Jane Doe.pdf"


def _store() -> RedisJobStore:
    server = fakeredis.FakeServer()
    return RedisJobStore(client=fake_redis.FakeRedis(server=server, decode_responses=True))


def test_get_job_key_normalizes_the_file_name():
    assert RedisJobStore.get_job_key("Resume/Folder/Jane Doe.PDF ") == "resume_job:jane doe.pdf"


async def test_init_or_get_state_creates_a_new_job_on_first_call():
    store = _store()

    state = await store.init_or_get_state(RESUME_PATH)

    assert state == {
        "file_name": "Jane Doe.pdf",
        "resume_path": RESUME_PATH,
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
    for field in RedisJobStore.EXTRACTION_FIELDS:
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
    assert status.missing_fields == list(RedisJobStore.EXTRACTION_FIELDS)


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
    assert status.missing_fields == list(RedisJobStore.EXTRACTION_FIELDS)


async def test_get_status_reports_has_content_true_once_content_is_saved():
    store = _store()
    await store.init_or_get_state(RESUME_PATH)
    await store.save_content(RESUME_PATH, "text")

    status = await store.get_status(RESUME_PATH)

    assert status.has_content is True
    assert status.missing_fields == list(RedisJobStore.EXTRACTION_FIELDS)


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
        resume_path=RESUME_PATH,
        session_id="session-99",
        is_completed=False,
        content="raw text",
        technical_skills={"skills": ["python"]},
        soft_skills=None,
        certifications=None,
        languages=None,
        errors={"languages": "timeout"},
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
    settings = RedisSettings(_env_file=None, host="redis.internal", password="secret", db=2)

    store = RedisJobStore(settings=settings)

    kwargs = store.redis.connection_pool.connection_kwargs
    assert kwargs["host"] == "redis.internal"
    assert kwargs["password"] == "secret"
    assert kwargs["db"] == 2


def test_redis_job_store_uses_cached_settings_when_none_given():
    get_redis_settings.cache_clear()

    store = RedisJobStore()

    assert store.redis.connection_pool.connection_kwargs["host"] == get_redis_settings().host
    get_redis_settings.cache_clear()
