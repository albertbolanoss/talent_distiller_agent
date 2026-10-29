"""Tests for the mocked parallel-extraction MCP tools."""

import json

import pytest

import candidate_match_agent_cli.tools.extraction_mocks as extraction_mocks_module
from candidate_match_agent_cli.tools.extraction_mocks import (
    _should_simulate_failure,
    extract_certifications,
    extract_languages,
    extract_soft_skills,
    extract_technical_skills,
)

RESUME_PATH = "resume/jane.pdf"


@pytest.fixture(autouse=True)
def _isolated_tracker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives each test its own failure-tracking set, independent of test execution order."""
    monkeypatch.setattr(extraction_mocks_module, "_FAILED_ONCE_TRACKER", set())


def test_should_simulate_failure_is_false_when_the_env_var_is_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_FAIL_ONCE_FIELDS", raising=False)

    assert _should_simulate_failure("technical_skills") is False


def test_should_simulate_failure_is_true_once_then_false_for_a_targeted_field(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MOCK_FAIL_ONCE_FIELDS", "certifications, languages")

    assert _should_simulate_failure("certifications") is True
    assert _should_simulate_failure("certifications") is False


def test_should_simulate_failure_is_false_for_a_field_not_in_the_target_list(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MOCK_FAIL_ONCE_FIELDS", "certifications")

    assert _should_simulate_failure("languages") is False


async def test_extract_technical_skills_returns_the_mocked_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_FAIL_ONCE_FIELDS", raising=False)

    result = await extract_technical_skills.handler({"resume_path": RESUME_PATH})

    payload = json.loads(result["content"][0]["text"])
    assert "languages" in payload
    assert "frameworks" in payload


async def test_extract_technical_skills_simulates_a_failure_when_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MOCK_FAIL_ONCE_FIELDS", "technical_skills")

    result = await extract_technical_skills.handler({"resume_path": RESUME_PATH})

    assert result["is_error"] is True
    assert "Simulated MCP timeout" in result["content"][0]["text"]


async def test_extract_soft_skills_returns_the_mocked_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_FAIL_ONCE_FIELDS", raising=False)

    result = await extract_soft_skills.handler({"resume_path": RESUME_PATH})

    payload = json.loads(result["content"][0]["text"])
    assert "soft_skills" in payload


async def test_extract_soft_skills_simulates_a_failure_when_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_FAIL_ONCE_FIELDS", "soft_skills")

    result = await extract_soft_skills.handler({"resume_path": RESUME_PATH})

    assert result["is_error"] is True
    assert "Simulated MCP error" in result["content"][0]["text"]


async def test_extract_certifications_returns_the_mocked_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_FAIL_ONCE_FIELDS", raising=False)

    result = await extract_certifications.handler({"resume_path": RESUME_PATH})

    payload = json.loads(result["content"][0]["text"])
    assert "certifications" in payload


async def test_extract_certifications_simulates_a_failure_when_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MOCK_FAIL_ONCE_FIELDS", "certifications")

    result = await extract_certifications.handler({"resume_path": RESUME_PATH})

    assert result["is_error"] is True
    assert "Simulated MCP connection drop" in result["content"][0]["text"]


async def test_extract_languages_returns_the_mocked_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_FAIL_ONCE_FIELDS", raising=False)

    result = await extract_languages.handler({"resume_path": RESUME_PATH})

    payload = json.loads(result["content"][0]["text"])
    assert "languages" in payload


async def test_extract_languages_simulates_a_failure_when_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_FAIL_ONCE_FIELDS", "languages")

    result = await extract_languages.handler({"resume_path": RESUME_PATH})

    assert result["is_error"] is True
    assert "Simulated MCP crash" in result["content"][0]["text"]
