"""Tests for the API server entrypoint."""

import pytest

import candidate_match_agent_cli.api.main as api_main_module


def test_main_serves_the_app_on_the_port_env_var(monkeypatch: pytest.MonkeyPatch):
    calls = []
    sentinel_app = object()

    monkeypatch.setattr(api_main_module, "create_app", lambda: sentinel_app)
    monkeypatch.setattr(api_main_module.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    monkeypatch.setenv("PORT", "9000")

    api_main_module.main()

    assert calls == [(sentinel_app, {"host": "0.0.0.0", "port": 9000})]


def test_main_defaults_to_port_8080_when_the_env_var_is_unset(monkeypatch: pytest.MonkeyPatch):
    calls = []
    sentinel_app = object()

    monkeypatch.setattr(api_main_module, "create_app", lambda: sentinel_app)
    monkeypatch.setattr(api_main_module.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    monkeypatch.delenv("PORT", raising=False)

    api_main_module.main()

    assert calls == [(sentinel_app, {"host": "0.0.0.0", "port": 8080})]
