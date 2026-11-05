"""Shared JSONL append helper backing the prompt log and agent transcript writers."""

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

SERVICE_NAME = "talent_distiller_agent"


def append_jsonl(directory: str, file_stem: str, record: dict[str, Any]) -> None:
    """Appends one JSON line to `{directory}/{file_stem}.jsonl`, creating the directory if needed."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with (path / f"{file_stem}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def utc_now_iso() -> str:
    """Returns the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()
