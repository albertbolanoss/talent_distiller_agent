"""Shared multipart-upload handling used by the resume and job-posting endpoints."""

import uuid
from pathlib import Path

import anyio
from labs_agent_lib.file_reader import SUPPORTED_EXTENSIONS
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse

FORM_FIELD = "file"


async def handle_upload(request: Request, destination_dir: Path) -> JSONResponse:
    """Accepts a multipart upload and stores it under `destination_dir`."""
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

    destination = _unique_destination(destination_dir, filename)
    await anyio.to_thread.run_sync(_write_file, destination, content)

    return JSONResponse({"filename": destination.name, "size": len(content)}, status_code=201)


def _unique_destination(directory: Path, filename: str) -> Path:
    """Returns `directory / filename`, or a uuid-suffixed variant if that path is already taken."""
    destination = directory / filename
    if not destination.exists():
        return destination

    stem, suffix = Path(filename).stem, Path(filename).suffix
    return directory / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"


def _write_file(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
