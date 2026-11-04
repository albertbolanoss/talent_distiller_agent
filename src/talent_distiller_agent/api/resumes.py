"""Upload endpoint that saves candidate resumes into the configured resume directory."""

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from talent_distiller_agent.settings import get_settings

from ._uploads import FORM_FIELD, handle_upload

__all__ = ["FORM_FIELD", "upload_resume"]


async def upload_resume(request: Request) -> JSONResponse:
    """Accepts a multipart upload and stores it under `settings.resume_dir`.

    This endpoint only validates and persists the file - the background resume-processing
    loop (`process_only_resumes`) picks it up on its next poll.
    """
    return await handle_upload(request, Path(get_settings().resume_dir))
