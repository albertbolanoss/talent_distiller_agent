"""Tests for the coordinator's orchestration of a single resume-processing turn."""

import pytest

import candidate_match_agent_cli.coordinators.coordinator as coordinator_module
from candidate_match_agent_cli.coordinators import run_coordinator
from candidate_match_agent_cli.storage import UnifiedResumeJob
from labs_agent_lib.agent_environment.agent_environment import AgentEnvironment


class _FakeSettings:
    coordinator_model = "model-x"
    coordinator_processed_folder = "resume/processed"
    coordinator_failed_folder = "resume/failed"
    coordinator_max_revision_number = 3


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

    def __init__(self, unified_result: UnifiedResumeJob) -> None:
        self._unified_result = unified_result
        self.closed = False

    async def __aenter__(self) -> "_FakeTracker":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.closed = True
        return False

    async def unify_by_filename(self, resume_path: str) -> UnifiedResumeJob:
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

        async def pre_execution_hook(self, resume_path: str) -> list[str]:
            return allowed_tools

        def build_sdk_hooks(self, resume_path: str) -> dict:
            return hooks or {}

        async def post_execution_hook(
            self, resume_path: str, session_id: str | None, stop_reason: str | None = None
        ) -> None:
            self.post_calls.append((resume_path, session_id, stop_reason))

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
        resume_path="resume/jane.pdf",
        session_id="session-123",
        is_completed=True,
        content="Candidate ✔ résumé",
    )
    expected_tracker = _FakeTracker(unified_result)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory(
        ["mcp__file-reader__read_document", "mcp__tech-skills-agent__extract_technical_skills"],
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

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda: expected_tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", fake_client_factory)
    monkeypatch.setattr(coordinator_module, "process_coordinator_stream", fake_process_coordinator_stream)

    result = await run_coordinator("resume/jane.pdf")

    assert result == unified_result.model_dump()
    assert expected_tracker.closed

    client = created_clients[0]
    assert client.queried_with == (
        "<resume_path>resume/jane.pdf</resume_path>\n"
        "<pending_tools>mcp__file-reader__read_document, "
        "mcp__tech-skills-agent__extract_technical_skills</pending_tools>"
    )
    assert client.options.model == "model-x"
    assert client.options.env == {"FOO": "bar"}
    assert client.options.system_prompt == coordinator_module.COORDINATOR_ORCHESTRATION_PROMPT
    assert client.options.allowed_tools == [
        "mcp__file-reader__read_document",
        "mcp__tech-skills-agent__extract_technical_skills",
    ]
    assert client.options.mcp_servers["file-reader"]["name"] == "file-reader"
    assert client.options.hooks == {"PreToolUse": []}

    assert guardrail_instances[0].post_calls == [("resume/jane.pdf", "session-123", "end_turn")]


async def test_skips_the_agent_entirely_when_the_guardrail_returns_no_tools(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_common(monkeypatch)
    unified_result = UnifiedResumeJob(file_name="jane.pdf", resume_path="resume/jane.pdf", is_completed=True)
    tracker = _FakeTracker(unified_result)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory([])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("ClaudeSDKClient must not be constructed")

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda: tracker)
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
    unified_result = UnifiedResumeJob(file_name="jane.pdf", resume_path="resume/jane.pdf", is_completed=False)
    tracker = _FakeTracker(unified_result)
    guardrail_cls, guardrail_instances = _fake_guardrail_factory(["mcp__file-reader__read_document"])

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(coordinator_module, "RedisJobStore", lambda: tracker)
    monkeypatch.setattr(coordinator_module, "CoordinatorGuardrail", guardrail_cls)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", boom)

    result = await run_coordinator("resume/jane.pdf")

    assert result == unified_result.model_dump()
    assert tracker.closed
    assert guardrail_instances[0].post_calls == []
