"""Starlette app: the resume/job-posting upload API plus the in-process processing loop.

Both run in the same process so that a document uploaded to a pod is processed by that
same pod's poll loop, with no shared storage required across replicas.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..main import start_process
from .job_postings import upload_job_posting
from .resumes import upload_resume


async def health(_request: Request) -> JSONResponse:
    """Liveness/readiness probe target."""
    return JSONResponse({"status": "ok"})


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
    """Runs the resume/job-posting processing poll loop for the lifetime of the app."""
    task = asyncio.create_task(start_process())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/resume", upload_resume, methods=["POST"]),
            Route("/job_posting", upload_job_posting, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
