"""Tests for the coordinator's pre/post-execution and SDK tool-use guardrails."""

import pytest

import candidate_match_agent_cli.guardrails.coordinator_guardrails as guardrails_module
from candidate_match_agent_cli.guardrails import CoordinatorGuardrail
from candidate_match_agent_cli.storage.redis_job_store import JobStatus
from candidate_match_agent_cli.tools import READ_DOCUMENT_TOOL_NAME

RESUME_PATH = "resume/jane.pdf"


class _FakeSettings:
    coordinator_processed_folder = "resume/processed"
    coordinator_failed_folder = "resume/failed"
    coordinator_max_revision_number = 3


class _FakeTracker:
    """Stands in for `RedisJobStore` without touching a real Redis server."""

    def __init__(self, status: JobStatus, *, increment_result: int = 1) -> None:
        self._status = status
        self._increment_result = increment_result
        self.save_session_calls: list[tuple[str, bool, str | None]] = []

    async def get_status(self, resume_path: str) -> JobStatus:
        return self._status

    async def increment_attempts(self, resume_path: str) -> int:
        return self._increment_result

    async def save_session_and_completion(
        self, resume_path: str, is_completed: bool, session_id: str | None = None
    ) -> None:
        self.save_session_calls.append((resume_path, is_completed, session_id))


def _patch_file_writer(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        guardrails_module, "file_writer", lambda path, folder: calls.append((path, folder))
    )
    return calls


async def test_pre_execution_hook_marks_processed_and_returns_no_tools_when_already_completed(
    monkeypatch: pytest.MonkeyPatch,
):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(resume_path=RESUME_PATH, revision_number=1, has_content=True, missing_fields=[])
    tracker = _FakeTracker(status)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(RESUME_PATH)

    assert allowed_tools == []
    assert tracker.save_session_calls == [(RESUME_PATH, True, None)]
    assert file_writer_calls == [(RESUME_PATH, "resume/processed")]


async def test_pre_execution_hook_marks_failed_when_revision_exceeds_max(
    monkeypatch: pytest.MonkeyPatch,
):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=RESUME_PATH, revision_number=0, has_content=False, missing_fields=["languages"]
    )
    tracker = _FakeTracker(status, increment_result=4)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(RESUME_PATH)

    assert allowed_tools == []
    assert file_writer_calls == [(RESUME_PATH, "resume/failed")]


async def test_pre_execution_hook_requests_read_tool_when_content_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=RESUME_PATH,
        revision_number=0,
        has_content=False,
        missing_fields=["technical_skills", "languages"],
    )
    tracker = _FakeTracker(status, increment_result=1)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(RESUME_PATH)

    assert allowed_tools == [
        READ_DOCUMENT_TOOL_NAME,
        "mcp__tech-skills-agent__extract_technical_skills",
        "mcp__lang-agent__extract_languages",
    ]


async def test_pre_execution_hook_skips_read_tool_when_content_is_already_present(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=["languages"]
    )
    tracker = _FakeTracker(status, increment_result=1)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(RESUME_PATH)

    assert allowed_tools == ["mcp__lang-agent__extract_languages"]


async def test_post_execution_hook_marks_processed_when_completed(monkeypatch: pytest.MonkeyPatch):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(resume_path=RESUME_PATH, revision_number=1, has_content=True, missing_fields=[])
    tracker = _FakeTracker(status)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    await guardrail.post_execution_hook(RESUME_PATH, session_id="session-1", stop_reason="end_turn")

    assert tracker.save_session_calls == [(RESUME_PATH, True, "session-1")]
    assert file_writer_calls == [(RESUME_PATH, "resume/processed")]


async def test_post_execution_hook_marks_failed_when_max_revision_reached_and_incomplete(
    monkeypatch: pytest.MonkeyPatch,
):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=RESUME_PATH, revision_number=3, has_content=True, missing_fields=["languages"]
    )
    tracker = _FakeTracker(status)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    await guardrail.post_execution_hook(RESUME_PATH, session_id=None)

    assert file_writer_calls == [(RESUME_PATH, "resume/failed")]


async def test_post_execution_hook_does_nothing_extra_when_incomplete_and_under_max_revision(
    monkeypatch: pytest.MonkeyPatch,
):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=RESUME_PATH, revision_number=1, has_content=True, missing_fields=["languages"]
    )
    tracker = _FakeTracker(status)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    await guardrail.post_execution_hook(RESUME_PATH, session_id=None)

    assert tracker.save_session_calls == [(RESUME_PATH, False, None)]
    assert file_writer_calls == []


def test_build_sdk_hooks_registers_a_single_pre_tool_use_matcher_for_extraction_tools():
    tracker = _FakeTracker(
        JobStatus(resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=[])
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    hooks = guardrail.build_sdk_hooks(RESUME_PATH)

    assert list(hooks.keys()) == ["PreToolUse"]
    matcher = hooks["PreToolUse"][0]
    assert isinstance(matcher.matcher, str)
    assert set(matcher.matcher.split("|")) == {
        "mcp__tech-skills-agent__extract_technical_skills",
        "mcp__soft-skills-agent__extract_soft_skills",
        "mcp__certs-agent__extract_certifications",
        "mcp__lang-agent__extract_languages",
    }
    assert len(matcher.hooks) == 1


async def test_build_sdk_hooks_denies_when_resume_content_is_not_yet_in_redis():
    tracker = _FakeTracker(
        JobStatus(resume_path=RESUME_PATH, revision_number=0, has_content=False, missing_fields=["languages"])
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = guardrail.build_sdk_hooks(RESUME_PATH)["PreToolUse"][0].hooks[0]

    result = await hook_fn(
        {"tool_name": "mcp__lang-agent__extract_languages"}, "tool-use-1", {"signal": None}
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert READ_DOCUMENT_TOOL_NAME in output["permissionDecisionReason"]


async def test_build_sdk_hooks_denies_a_duplicate_call_for_an_already_checkpointed_field():
    tracker = _FakeTracker(
        JobStatus(resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=[])
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = guardrail.build_sdk_hooks(RESUME_PATH)["PreToolUse"][0].hooks[0]

    result = await hook_fn(
        {"tool_name": "mcp__lang-agent__extract_languages"}, "tool-use-1", {"signal": None}
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "already checkpointed" in output["permissionDecisionReason"]


async def test_build_sdk_hooks_allows_a_call_for_a_still_missing_field():
    tracker = _FakeTracker(
        JobStatus(
            resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=["languages"]
        )
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = guardrail.build_sdk_hooks(RESUME_PATH)["PreToolUse"][0].hooks[0]

    result = await hook_fn(
        {"tool_name": "mcp__lang-agent__extract_languages"}, "tool-use-1", {"signal": None}
    )

    assert result == {}
