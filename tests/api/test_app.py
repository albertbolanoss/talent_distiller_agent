"""Tests for the Starlette app wiring the resume-upload API and the background poll loop."""

import asyncio

from starlette.testclient import TestClient

import talent_distiller_agent.api.app as app_module


def test_healthz_reports_ok():
    with TestClient(app_module.create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_lifespan_starts_and_cancels_the_background_resume_processing_loop(monkeypatch):
    started = []
    cancelled = []

    async def fake_start_process() -> None:
        started.append(True)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr(app_module, "start_process", fake_start_process)

    with TestClient(app_module.create_app()) as client:
        response = client.get("/healthz")
        assert response.status_code == 200

    assert started == [True]
    assert cancelled == [True]
