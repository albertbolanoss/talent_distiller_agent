"""Tests for the coordinator's single document-read turn."""

import pytest

import candidate_match_agent.coordinators.coordinator as coordinator_module
from candidate_match_agent.coordinators import run_coordinator
from candidate_match_agent.libs.agent_environment.agent_environment import AgentEnvironment


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


async def test_builds_options_queries_and_returns_the_tool_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    sentinel_settings = object()
    created_clients: list[_FakeClaudeSDKClient] = []

    def fake_client_factory(options) -> _FakeClaudeSDKClient:
        client = _FakeClaudeSDKClient(options)
        created_clients.append(client)
        return client

    async def fake_process_coordinator_stream(client):
        assert client is created_clients[-1]
        return "Candidate ✔ résumé", "end_turn", "session-123"

    def fake_get_agent_environment(settings) -> AgentEnvironment:
        assert settings is sentinel_settings
        return AgentEnvironment(env={"FOO": "bar"})

    monkeypatch.setattr(coordinator_module, "get_settings", lambda: sentinel_settings)
    monkeypatch.setattr(coordinator_module, "get_agent_environment", fake_get_agent_environment)
    monkeypatch.setattr(coordinator_module, "ClaudeSDKClient", fake_client_factory)
    monkeypatch.setattr(coordinator_module, "process_coordinator_stream", fake_process_coordinator_stream)

    result = await run_coordinator("model-x", "resume/jane.pdf")

    assert result == {"resume_path": "resume/jane.pdf", "content": "Candidate ✔ résumé"}
    assert "Candidate ✔ résumé" in capsys.readouterr().out

    client = created_clients[0]
    assert client.queried_with == "<resume_path>resume/jane.pdf</resume_path>"
    assert client.options.model == "model-x"
    assert client.options.env == {"FOO": "bar"}
    assert client.options.system_prompt == coordinator_module.DOCUMENT_READ_PROMPT
    assert client.options.allowed_tools == ["mcp__file-reader__read_document"]
    assert client.options.mcp_servers["file-reader"]["name"] == "file-reader"
