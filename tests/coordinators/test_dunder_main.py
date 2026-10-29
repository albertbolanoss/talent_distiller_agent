"""Tests for the `python -m candidate_match_agent_cli.coordinators <resume_path>` CLI."""

import sys

import pytest

import candidate_match_agent_cli.coordinators.__main__ as dunder_main


def test_parses_argv_and_invokes_run_coordinator_with_them(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def fake_run_coordinator(resume_path: str) -> dict:
        calls.append(resume_path)
        return {"resume_path": resume_path, "content": "stub"}

    monkeypatch.setattr(dunder_main, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(sys, "argv", ["candidate-match-agent-cli-coordinator", "resume.pdf"])

    dunder_main.main()

    assert calls == ["resume.pdf"]


def test_missing_arguments_exit_with_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "argv", ["candidate-match-agent-cli-coordinator"])

    with pytest.raises(SystemExit) as exc_info:
        dunder_main.main()

    assert exc_info.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()
