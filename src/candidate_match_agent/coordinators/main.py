"""Direct entrypoint: edit MODEL/RESUME_PATH below, then run this module.

    uv run python -m candidate_match_agent.coordinators.main
"""

import asyncio

from candidate_match_agent.coordinators.coordinator import run_coordinator

MODEL = "us.anthropic.claude-sonnet-5"
RESUME_PATH = "resume/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf"


if __name__ == "__main__":
    asyncio.run(run_coordinator(MODEL, RESUME_PATH))
