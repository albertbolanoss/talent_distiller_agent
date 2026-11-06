"""Tests for the Starlette app wiring the upload API and the background poll loop."""

import asyncio

from starlette.testclient import TestClient

import talent_distiller_agent.api.app as app_module


def test_healthz_reports_ok():
    with TestClient(app_module.create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_job_posting_route_is_wired_to_the_upload_handler():
    app = app_module.create_app()

    route = next(route for route in app.routes if route.path == "/job_posting")

    assert route.endpoint is app_module.upload_job_posting
    assert route.methods == {"POST"}


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
