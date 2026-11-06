"""Entrypoint: serves the resume-upload API and runs the resume-processing loop.

    uv run talent-distiller-agent-api
"""

import os

import uvicorn

from .app import create_app

DEFAULT_PORT = 8080


def main() -> None:
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
