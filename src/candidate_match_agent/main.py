"""Entrypoint: periodically reads resume files via the coordinator agent."""

import asyncio
from pathlib import Path

from .coordinators.coordinator import run_coordinator
from .libs import get_settings
from .libs.file_reader import SUPPORTED_EXTENSIONS

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


def main() -> None:
    asyncio.run(process_resumes())


if __name__ == "__main__":
    main()
