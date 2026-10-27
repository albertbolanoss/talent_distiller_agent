"""Background loop: periodically reads resume files via the coordinator agent.

Started by `candidate_match_agent_cli.api.app`'s lifespan, inside the same process as the
resume-upload API - see `candidate-match-agent-api` in `[project.scripts]`.
"""

import asyncio
from pathlib import Path

from labs_agent_lib import get_settings
from labs_agent_lib.file_reader import SUPPORTED_EXTENSIONS

from .coordinators.coordinator import run_coordinator

MODEL = "us.anthropic.claude-sonnet-5"


async def process_resumes() -> None:
    settings = get_settings()
    resume_dir = Path(settings.resume_dir)

    while True:
        resume_paths = sorted(
            path
            for path in resume_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )[: settings.resume_max_files_per_batch]
        await asyncio.gather(
            *(run_coordinator(MODEL, str(resume_path)) for resume_path in resume_paths)
        )

        await asyncio.sleep(settings.resume_poll_interval_seconds)
