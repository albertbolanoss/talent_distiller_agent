"""Tests for the coordinator's pre/post-execution and SDK tool-use guardrails."""

import pytest
from claude_agent_sdk import HookCallback, HookMatcher

import candidate_match_agent_cli.guardrails.coordinator_guardrails as guardrails_module
from candidate_match_agent_cli.guardrails import CoordinatorGuardrail
from candidate_match_agent_cli.mcp_client import EXTRACTION_TOOL_TO_FIELD
from candidate_match_agent_cli.storage import DocumentType
from candidate_match_agent_cli.storage.job_store import JobStatus

RESUME_PATH = "resume/jane.pdf"
JOB_POSTING_PATH = "job_posting/backend-engineer.pdf"
EXTRACT_LANGUAGES_TOOL = "mcp__candidate-skill-agent__extract_languages"


def _hook_for(hooks: dict[str, list[HookMatcher]], tool_name: str) -> HookCallback:
    """Finds the `PreToolUse` callback declared for `tool_name`."""
    for matcher in hooks["PreToolUse"]:
        if matcher.matcher == tool_name:
            return matcher.hooks[0]
    raise AssertionError(f"no PreToolUse hook registered for {tool_name}")


class _FakeSettings:
    resume_dir = "resume"
    job_posting_dir = "job_posting"
    coordinator_processed_folder = "resume/processed"
    coordinator_failed_folder = "resume/failed"
    job_posting_processed_folder = "job_posting/processed"
    job_posting_failed_folder = "job_posting/failed"
    coordinator_max_revision_number = 3


class _FakeTracker:
    """Stands in for `JobStore` without touching a real Redis server."""

    def __init__(
        self,
        status: JobStatus,
        *,
        doc_type: DocumentType = DocumentType.RESUME,
        increment_result: int = 1,
    ) -> None:
        self.doc_type = doc_type
        self._status = status
        self._increment_result = increment_result
        self.save_session_calls: list[tuple[str, bool, str | None]] = []

    async def get_status(self, file_path: str) -> JobStatus:
        return self._status

    async def wait_for_content(self, file_path: str) -> JobStatus:
        return await self.get_status(file_path)

    async def increment_attempts(self, file_path: str) -> int:
        return self._increment_result

    async def save_session_and_completion(
        self, file_path: str, is_completed: bool, session_id: str | None = None
    ) -> None:
        self.save_session_calls.append((file_path, is_completed, session_id))

    def get_target_fields_for_base_field(self, base_field: str) -> tuple[str, ...]:
        if self.doc_type == DocumentType.JOB_POSTING:
            return (base_field, f"desirable_{base_field}")
        return (base_field,)


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


async def test_pre_execution_hook_marks_processed_in_the_job_posting_folder_when_completed(
    monkeypatch: pytest.MonkeyPatch,
):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=JOB_POSTING_PATH, revision_number=1, has_content=True, missing_fields=[]
    )
    tracker = _FakeTracker(status, doc_type=DocumentType.JOB_POSTING)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(JOB_POSTING_PATH)

    assert allowed_tools == []
    assert file_writer_calls == [(JOB_POSTING_PATH, "job_posting/processed")]


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


async def test_pre_execution_hook_marks_failed_in_the_job_posting_folder_when_revision_exceeds_max(
    monkeypatch: pytest.MonkeyPatch,
):
    file_writer_calls = _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=JOB_POSTING_PATH, revision_number=0, has_content=False, missing_fields=["languages"]
    )
    tracker = _FakeTracker(status, doc_type=DocumentType.JOB_POSTING, increment_result=4)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(JOB_POSTING_PATH)

    assert allowed_tools == []
    assert file_writer_calls == [(JOB_POSTING_PATH, "job_posting/failed")]


async def test_pre_execution_hook_returns_deduplicated_tools_for_missing_fields(
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
        "mcp__candidate-skill-agent__extract_technical_skills",
        "mcp__candidate-skill-agent__extract_languages",
    ]


async def test_pre_execution_hook_maps_desirable_fields_to_their_base_mcp_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_file_writer(monkeypatch)
    status = JobStatus(
        resume_path=JOB_POSTING_PATH,
        revision_number=0,
        has_content=False,
        missing_fields=["languages", "desirable_languages"],
    )
    tracker = _FakeTracker(status, doc_type=DocumentType.JOB_POSTING, increment_result=1)
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    allowed_tools = await guardrail.pre_execution_hook(JOB_POSTING_PATH)

    assert allowed_tools == ["mcp__candidate-skill-agent__extract_languages"]


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


def test_build_sdk_hooks_registers_one_pre_tool_use_matcher_per_extraction_tool():
    tracker = _FakeTracker(
        JobStatus(resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=[])
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())

    hooks = guardrail.build_sdk_hooks(RESUME_PATH)

    assert list(hooks.keys()) == ["PreToolUse"]
    matchers = hooks["PreToolUse"]
    assert {matcher.matcher for matcher in matchers} == set(EXTRACTION_TOOL_TO_FIELD)
    assert all(len(matcher.hooks) == 1 for matcher in matchers)


async def test_build_sdk_hooks_denies_when_resume_content_is_not_yet_in_redis():
    tracker = _FakeTracker(
        JobStatus(resume_path=RESUME_PATH, revision_number=0, has_content=False, missing_fields=["languages"])
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = _hook_for(guardrail.build_sdk_hooks(RESUME_PATH), EXTRACT_LANGUAGES_TOOL)

    result = await hook_fn(
        {"tool_name": EXTRACT_LANGUAGES_TOOL}, "tool-use-1", {"signal": None}
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "formatted_resume" in output["permissionDecisionReason"]


async def test_build_sdk_hooks_uses_the_custom_formatted_tag_in_the_deny_reason():
    tracker = _FakeTracker(
        JobStatus(resume_path=JOB_POSTING_PATH, revision_number=0, has_content=False, missing_fields=["languages"]),
        doc_type=DocumentType.JOB_POSTING,
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = _hook_for(
        guardrail.build_sdk_hooks(JOB_POSTING_PATH, formatted_tag="formatted_job_posting"),
        EXTRACT_LANGUAGES_TOOL,
    )

    result = await hook_fn(
        {"tool_name": EXTRACT_LANGUAGES_TOOL}, "tool-use-1", {"signal": None}
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "formatted_job_posting" in output["permissionDecisionReason"]


async def test_build_sdk_hooks_denies_a_duplicate_call_for_an_already_checkpointed_field():
    tracker = _FakeTracker(
        JobStatus(resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=[])
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = _hook_for(guardrail.build_sdk_hooks(RESUME_PATH), EXTRACT_LANGUAGES_TOOL)

    result = await hook_fn(
        {"tool_name": EXTRACT_LANGUAGES_TOOL}, "tool-use-1", {"signal": None}
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "already checkpointed" in output["permissionDecisionReason"]


async def test_build_sdk_hooks_denies_a_duplicate_call_when_only_the_desirable_field_remains():
    tracker = _FakeTracker(
        JobStatus(resume_path=JOB_POSTING_PATH, revision_number=0, has_content=True, missing_fields=[]),
        doc_type=DocumentType.JOB_POSTING,
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = _hook_for(guardrail.build_sdk_hooks(JOB_POSTING_PATH), EXTRACT_LANGUAGES_TOOL)

    result = await hook_fn(
        {"tool_name": EXTRACT_LANGUAGES_TOOL}, "tool-use-1", {"signal": None}
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"


async def test_build_sdk_hooks_allows_a_call_for_a_still_missing_field():
    tracker = _FakeTracker(
        JobStatus(
            resume_path=RESUME_PATH, revision_number=0, has_content=True, missing_fields=["languages"]
        )
    )
    guardrail = CoordinatorGuardrail(tracker=tracker, settings=_FakeSettings())
    hook_fn = _hook_for(guardrail.build_sdk_hooks(RESUME_PATH), EXTRACT_LANGUAGES_TOOL)

    result = await hook_fn(
        {"tool_name": EXTRACT_LANGUAGES_TOOL}, "tool-use-1", {"signal": None}
    )

    assert result == {}
