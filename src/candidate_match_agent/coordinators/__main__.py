"""CLI entrypoint: `python -m candidate_match_agent.coordinators <model> <resume_path>`."""

import argparse
import asyncio

from .coordinator import run_coordinator


def main() -> None:
    parser = argparse.ArgumentParser(description="Read a resume document via the coordinator agent.")
    parser.add_argument("model", help="Model name/id to use for the agent.")
    parser.add_argument("resume_path", help="Path to the resume document to read.")
    args = parser.parse_args()

    asyncio.run(run_coordinator(args.model, args.resume_path))


if __name__ == "__main__":
    main()
