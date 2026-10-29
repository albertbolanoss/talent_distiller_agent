"""Background loop: periodically reads resume files via the coordinator agent.

Started by `candidate_match_agent_cli.api.app`'s lifespan, inside the same process as the
resume-upload API - see `candidate-match-agent-api` in `[project.scripts]`.
"""

import asyncio
from pathlib import Path

from labs_agent_lib import get_logger
from labs_agent_lib.file_reader import SUPPORTED_EXTENSIONS
from candidate_match_agent_cli.settings import get_settings
from .coordinators.coordinator import run_coordinator

logger = get_logger(__name__)

MODULE = "[ResumePoller]"


def get_creation_time(path: Path) -> float:
    """Obtiene la fecha de creación de forma segura y multiplataforma."""
    stat = path.stat()
    
    if hasattr(stat, 'st_birthtime'):
        return stat.st_birthtime
    
    return stat.st_mtime


async def process_resumes() -> None:
    settings = get_settings()
    resume_dir = Path(settings.resume_dir)

    while True:
        try:
            resume_paths = sorted(
                (
                    path
                    for path in resume_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
                ),
                key=get_creation_time
            )[: settings.resume_max_files_per_batch]

            results = await asyncio.gather(
                *(run_coordinator(str(resume_path)) for resume_path in resume_paths),
                return_exceptions=True,
            )
            for resume_path, result in zip(resume_paths, results):
                if isinstance(result, BaseException):
                    logger.error("%s Failed to process %s", MODULE, resume_path, exc_info=result)
        except Exception:
            logger.exception("%s Poll loop iteration failed", MODULE)

        await asyncio.sleep(settings.resume_poll_interval_seconds)
