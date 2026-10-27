"""Centralized logging setup for the whole app (coordinators, subagent task events, MCP tools).

Usage: `logger = get_logger(__name__)` at module level, then `logger.debug/info/warning/error(...)`.
Verbosity is controlled by Settings.log_level (LABS_RESUME_AGENT_LOG_LEVEL) - set it to DEBUG to
see every step (tool calls, per-task progress) or leave it at INFO to only see the high-level
phases (task started/done, final results). Logs go to stderr, not stdout: mcp_server.py runs as
an MCP stdio subprocess, and anything printed to stdout there would corrupt the MCP protocol.
"""

import logging
import sys

from candidate_match_agent.libs.settings import get_settings

_ROOT_LOGGER_NAME = "candidate_match_agent"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(get_settings().log_level.value)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger in the labs_resume_agent hierarchy; pass __name__ from the call site."""
    _configure()
    return logging.getLogger(name)
