"""Upload endpoint that saves candidate resumes into the configured resume directory."""

import uuid
from pathlib import Path

import anyio
from labs_agent_lib.file_reader import SUPPORTED_EXTENSIONS
from talent_distiller_agent.settings import get_settings
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse

FORM_FIELD = "file"


async def upload_resume(request: Request) -> JSONResponse:
    """Accepts a multipart upload and stores it under `settings.resume_dir`.

    This endpoint only validates and persists the file - the background resume-processing
    loop (`process_resumes`) picks it up on its next poll.
    """
    async with request.form() as form:
        upload = form.get(FORM_FIELD)
        if upload is None or not isinstance(upload, UploadFile):
            return JSONResponse(
                {"error": f"Missing '{FORM_FIELD}' field in multipart form data."},
                status_code=400,
            )

        filename = Path(upload.filename or "").name
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            return JSONResponse(
                {
                    "error": f"Unsupported file type '{extension or '(none)'}'.",
                    "supported_extensions": SUPPORTED_EXTENSIONS,
                },
                status_code=400,
            )

        content = await upload.read()

    destination = _unique_destination(Path(get_settings().resume_dir), filename)
    await anyio.to_thread.run_sync(_write_file, destination, content)

    return JSONResponse({"filename": destination.name, "size": len(content)}, status_code=201)


def _unique_destination(resume_dir: Path, filename: str) -> Path:
    """Returns `resume_dir / filename`, or a uuid-suffixed variant if that path is already taken."""
    destination = resume_dir / filename
    if not destination.exists():
        return destination

    stem, suffix = Path(filename).stem, Path(filename).suffix
    return resume_dir / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"


def _write_file(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
