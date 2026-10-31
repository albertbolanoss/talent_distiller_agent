"""Tests for the coordinator's orchestration of a single resume/job-posting processing turn."""

import pytest

import candidate_match_agent_cli.coordinators.coordinator as coordinator_module
from candidate_match_agent_cli.coordinators import run_coordinator
from candidate_match_agent_cli.storage import DocumentType, UnifiedResumeJob
from candidate_match_agent_cli.storage.redis_job_store import JobStatus
from labs_agent_lib.agent_environment.agent_environment import AgentEnvironment


class _FakeSettings:
    coordinator_model = "model-x"
    coordinator_processed_folder = "resume/processed"
    coordinator_failed_folder = "resume/failed"
    job_posting_processed_folder = "job_posting/processed"
    job_posting_failed_folder = "job_posting/failed"
    coordinator_max_revision_number = 3
    skill_agent_mcp_url = "http://127.0.0.1:8000/mcp"


class _FakeClaudeSDKClient:
    """Records the options it was built with and the prompt it was queried with."""

    def __init__(self, options) -> None:
        self.options = options
        self.queried_with: str | None = None

    async def __aenter__(self) -> "_FakeClaudeSDKClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def query(self, prompt: str) -> None:
        self.queried_with = prompt


class _FakeTracker:
    """Stands in for `async with RedisJobStore() as tracker` without touching Redis."""

    def __init__(self, unified_result: UnifiedResumeJob, status: JobStatus | None = None) -> None:
        self._unified_result = unified_result
        self._status = status
        self.closed = False
        self.errors: list[tuple[str, str, str]] = []

    async def __aenter__(self) -> "_FakeTracker":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.closed = True
        return False

    async def get_status(self, file_path: str) -> JobStatus:
        return self._status

    async def save_agent_error(self, file_path: str, field: str, error_msg: str) -> None:
        self.errors.append((file_path, field, error_msg))

    async def unify_by_filename(self, file_path: str) -> UnifiedResumeJob:
        return self._unified_result


def _fake_guardrail_factory(allowed_tools: list[str], hooks: dict | None = None):
    """Builds a `CoordinatorGuardrail` stand-in, and the list its instances get recorded in."""
    instances: list["_FakeGuardrail"] = []

    class _FakeGuardrail:
        def __init__(self, tracker, settings) -> None:
            self.tracker = tracker
            self.settings = settings
            self.post_calls: list[tuple[str, str | None, str | None]] = []
            instances.append(self)

        async def pre_execution_hook(self, file_path: str) -> list[str]:
            return allowed_tools

        def build_sdk_hooks(self, file_path: str, formatted_tag: str = "formatted_resume") -> dict:
            return hooks or {}

        async def post_execution_hook(
            self, file_path: str, session_id: str | None, stop_reason: str | None = None
        ) -> None:
            self.post_calls.append((file_path, session_id, stop_reason))

    return _FakeGuardrail, instances


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coordinator_module, "get_agent_settings", lambda: object())
    monkeypatch.setattr(
        coordinator_module, "get_agent_environment", lambda settings: AgentEnvironment(env={"FOO": "bar"})
    )
    monkeypatch.setattr(coordinator_module, "get_settings", lambda: _FakeSettings())


async def test_builds_options_queries_and_processes_the_stream_when_tools_are_allowed(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_common(monkeypatch)
    created_clients: list[_FakeClaudeSDKClient] = []
    unified_result = UnifiedResumeJob(
        file_name="jane.pdf",
        file_path="resume/jane.pdf",
        session_id="session-123",
        is_completed=True,
        content="Candidate ✔ résumé",
    )
    status = JobStatus(
        resume_path="resume/jane.pdf", revision_number=1, has_content=False, missing_fields=["technical_skills"]
    )
    expected_tracker = _FakeTracker(unified_result, status=status)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory(
        ["mcp__candidate-skill-agent__extract_technical_skills"],
        hooks={"PreToolUse": []},
    )

    def fake_client_factory(options) -> _FakeClaudeSDKClient:
        client = _FakeClaudeSDKClient(options)
        created_clients.append(client)
        return client

    async def fake_process_coordinator_stream(client, tracker, resume_path: str):
        assert client is created_clients[-1]
        assert tracker is expected_tracker
        return "end_turn", "session-123"

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda doc_type: expected_tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", fake_client_factory)
    monkeypatch.setattr(coordinator_module, "process_coordinator_stream", fake_process_coordinator_stream)
    monkeypatch.setattr(coordinator_module, "extract_text", lambda file_path: "raw resume text")

    result = await run_coordinator("resume/jane.pdf")

    assert result == unified_result.model_dump()
    assert expected_tracker.closed

    client = created_clients[0]
    assert client.queried_with == (
        "<resume_path>resume/jane.pdf</resume_path>\n"
        "<resume_content>\nraw resume text\n</resume_content>\n"
        "<pending_tools>mcp__candidate-skill-agent__extract_technical_skills</pending_tools>"
    )
    assert client.options.model == "model-x"
    assert client.options.env == {"FOO": "bar"}
    assert client.options.system_prompt == coordinator_module.RESUME_COORDINATOR_ORCHESTRATION_PROMPT
    assert client.options.allowed_tools == ["mcp__candidate-skill-agent__extract_technical_skills"]
    assert client.options.mcp_servers == {
        coordinator_module.SKILL_AGENT_SERVER_NAME: {
            "type": "http",
            "url": "http://127.0.0.1:8000/mcp",
        }
    }
    assert client.options.hooks == {"PreToolUse": []}

    assert guardrail_instances[0].post_calls == [("resume/jane.pdf", "session-123", "end_turn")]


async def test_omits_resume_content_and_includes_missing_fields_for_a_job_posting_with_content(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_common(monkeypatch)
    unified_result = UnifiedResumeJob(
        file_name="job.pdf", file_path="job_posting/job.pdf", is_completed=False
    )
    status = JobStatus(
        resume_path="job_posting/job.pdf",
        revision_number=1,
        has_content=True,
        missing_fields=["desirable_languages"],
    )
    tracker = _FakeTracker(unified_result, status=status)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory(
        ["mcp__candidate-skill-agent__extract_languages"]
    )

    created_clients: list[_FakeClaudeSDKClient] = []

    def fake_client_factory(options) -> _FakeClaudeSDKClient:
        client = _FakeClaudeSDKClient(options)
        created_clients.append(client)
        return client

    async def fake_process_coordinator_stream(client, tracker, resume_path: str):
        return "end_turn", "session-1"

    def fail_if_called(file_path: str) -> str:
        raise AssertionError("extract_text must not be called when content already exists")

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda doc_type: tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", fake_client_factory)
    monkeypatch.setattr(coordinator_module, "process_coordinator_stream", fake_process_coordinator_stream)
    monkeypatch.setattr(coordinator_module, "extract_text", fail_if_called)

    await run_coordinator("job_posting/job.pdf", doc_type=DocumentType.JOB_POSTING)

    client = created_clients[0]
    assert client.queried_with == (
        "<job_posting_path>job_posting/job.pdf</job_posting_path>\n"
        "<pending_tools>mcp__candidate-skill-agent__extract_languages</pending_tools>\n"
        "<missing_fields>desirable_languages</missing_fields>"
    )
    assert client.options.system_prompt == coordinator_module.JOB_POSTING_COORDINATOR_ORCHESTRATION_PROMPT
    assert guardrail_instances[0].post_calls == [("job_posting/job.pdf", "session-1", "end_turn")]


async def test_records_an_error_and_raises_when_extracted_text_is_empty(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_common(monkeypatch)
    unified_result = UnifiedResumeJob(file_name="jane.pdf", file_path="resume/jane.pdf", is_completed=False)
    status = JobStatus(
        resume_path="resume/jane.pdf", revision_number=1, has_content=False, missing_fields=["languages"]
    )
    tracker = _FakeTracker(unified_result, status=status)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory(["mcp__candidate-skill-agent__extract_languages"])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("ClaudeSDKClient must not be constructed")

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda doc_type: tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", fail_if_called)
    monkeypatch.setattr(coordinator_module, "extract_text", lambda file_path: "   ")

    result = await run_coordinator("resume/jane.pdf")

    assert result == unified_result.model_dump()
    assert tracker.closed
    assert tracker.errors == [
        ("resume/jane.pdf", coordinator_module.JobRedisField.CONTENT, "extract_text returned empty content.")
    ]
    assert guardrail_instances[0].post_calls == []


async def test_skips_the_agent_entirely_when_the_guardrail_returns_no_tools(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_common(monkeypatch)
    unified_result = UnifiedResumeJob(file_name="jane.pdf", file_path="resume/jane.pdf", is_completed=True)
    tracker = _FakeTracker(unified_result)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory([])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("ClaudeSDKClient must not be constructed")

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda doc_type: tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", fail_if_called)

    result = await run_coordinator("resume/jane.pdf")

    assert result == unified_result.model_dump()
    assert tracker.closed
    assert guardrail_instances[0].post_calls == []


async def test_logs_and_still_returns_the_unified_result_when_the_agent_turn_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_common(monkeypatch)
    unified_result = UnifiedResumeJob(file_name="jane.pdf", file_path="resume/jane.pdf", is_completed=False)
    status = JobStatus(
        resume_path="resume/jane.pdf", revision_number=1, has_content=True, missing_fields=["languages"]
    )
    tracker = _FakeTracker(unified_result, status=status)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory(
        ["mcp__candidate-skill-agent__extract_languages"]
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda doc_type: tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", boom)

    result = await run_coordinator("resume/jane.pdf")

    assert result == unified_result.model_dump()
    assert tracker.closed
    assert guardrail_instances[0].post_calls == []


async def test_run_resume_coordinator_delegates_with_the_resume_doc_type(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, DocumentType]] = []

    async def fake_run_coordinator(file_path: str, doc_type: DocumentType = DocumentType.RESUME):
        calls.append((file_path, doc_type))
        return {"ok": True}

    monkeypatch.setattr(coordinator_module, "run_coordinator", fake_run_coordinator)

    result = await coordinator_module.run_resume_coordinator("resume/jane.pdf")

    assert result == {"ok": True}
    assert calls == [("resume/jane.pdf", DocumentType.RESUME)]


async def test_run_job_posting_coordinator_delegates_with_the_job_posting_doc_type(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, DocumentType]] = []

    async def fake_run_coordinator(file_path: str, doc_type: DocumentType = DocumentType.RESUME):
        calls.append((file_path, doc_type))
        return {"ok": True}

    monkeypatch.setattr(coordinator_module, "run_coordinator", fake_run_coordinator)

    result = await coordinator_module.run_job_posting_coordinator("job_posting/job.pdf")

    assert result == {"ok": True}
    assert calls == [("job_posting/job.pdf", DocumentType.JOB_POSTING)]
