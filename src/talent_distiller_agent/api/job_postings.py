"""Upload endpoint that saves job postings into the configured job-posting directory."""

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from talent_distiller_agent.settings import get_settings

from ._uploads import FORM_FIELD, handle_upload

__all__ = ["FORM_FIELD", "upload_job_posting"]


async def upload_job_posting(request: Request) -> JSONResponse:
    """Accepts a multipart upload and stores it under `settings.job_posting_dir`.

    This endpoint only validates and persists the file - the background job-posting-processing
    loop (`process_job_postings`) picks it up on its next poll.
    """
    return await handle_upload(request, Path(get_settings().job_posting_dir))
