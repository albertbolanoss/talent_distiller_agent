"""Starlette app: the resume-upload API plus the in-process resume-processing loop.

Both run in the same process so that a resume uploaded to a pod is processed by that
same pod's poll loop, with no shared storage required across replicas.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..main import process_resumes
from .resumes import upload_resume


async def health(_request: Request) -> JSONResponse:
    """Liveness/readiness probe target."""
    return JSONResponse({"status": "ok"})


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    """Runs the resume-processing poll loop for the lifetime of the app."""
    task = asyncio.create_task(process_resumes())
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
            Route("/resumes", upload_resume, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
