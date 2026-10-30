"""Background loop: periodically reads resume and job posting files via the coordinator agent.

Started by `candidate_match_agent_cli.api.app`'s lifespan, inside the same process as the
resume-upload API - see `candidate-match-agent-api` in `[project.scripts]`.
"""

import asyncio
from pathlib import Path

from labs_agent_lib import get_logger
from labs_agent_lib.file_reader import SUPPORTED_EXTENSIONS

from candidate_match_agent_cli.settings import get_settings
from candidate_match_agent_cli.storage import DocumentType

from .coordinators.coordinator import run_coordinator

logger = get_logger(__name__)

MODULE = "[DocumentPoller]"


def get_creation_time(path: Path) -> float:
    """Obtiene la fecha de creación de forma segura y multiplataforma."""
    stat = path.stat()

    if hasattr(stat, "st_birthtime"):
        return stat.st_birthtime

    return stat.st_mtime


async def _process_directory_batch(
    directory: Path,
    doc_type: DocumentType,
    max_files_per_batch: int,
) -> None:
    """Escanea un directorio y procesa un lote de archivos para el `DocumentType` indicado."""
    if not directory.exists():
        return

    file_paths = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=get_creation_time,
    )[:max_files_per_batch]

    if not file_paths:
        return

    results = await asyncio.gather(
        *(run_coordinator(str(file_path), doc_type=doc_type) for file_path in file_paths),
        return_exceptions=True,
    )
    for file_path, result in zip(file_paths, results):
        if isinstance(result, BaseException):
            logger.error(
                "%s [%s] Failed to process %s",
                MODULE,
                doc_type,
                file_path,
                exc_info=result,
            )


async def _poll_loop(
    directory: Path,
    doc_type: DocumentType,
    max_files_per_batch: int,
    poll_interval_seconds: float,
) -> None:
    """Bucle infinito de polling para un directorio específico."""
    directory.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            await _process_directory_batch(
                directory=directory,
                doc_type=doc_type,
                max_files_per_batch=max_files_per_batch,
            )
        except Exception:
            logger.exception("%s [%s] Poll loop iteration failed", MODULE, doc_type)

        await asyncio.sleep(poll_interval_seconds)


async def process_only_resumes() -> None:
    """Ejecuta el poller de la carpeta `resume`."""
    settings = get_settings()
    await _poll_loop(
        directory=Path(settings.resume_dir),
        doc_type=DocumentType.RESUME,
        max_files_per_batch=settings.resume_max_files_per_batch,
        poll_interval_seconds=settings.resume_poll_interval_seconds,
    )


async def process_job_postings() -> None:
    """Ejecuta el poller de la carpeta `job_posting`."""
    settings = get_settings()
    await _poll_loop(
        directory=Path(settings.job_posting_dir),
        doc_type=DocumentType.JOB_POSTING,
        max_files_per_batch=settings.job_posting_max_files_per_batch,
        poll_interval_seconds=settings.job_posting_poll_interval_seconds,
    )


async def start_process() -> None:
    """Punto de entrada invocado por el lifespan de la API: monitorea `resume` y `job_posting` en paralelo."""
    await asyncio.gather(
        process_only_resumes(),
        process_job_postings(),
    )
