"""MCP client wiring for the external candidate-skill-agent HTTP server."""

from .skill_agent import (
    EXTRACTION_TOOL_TO_FIELD,
    READ_DOCUMENT_TOOL_NAME,
    SKILL_AGENT_SERVER_NAME,
    get_skill_agent_mcp_server,
)

__all__ = [
    "EXTRACTION_TOOL_TO_FIELD",
    "READ_DOCUMENT_TOOL_NAME",
    "SKILL_AGENT_SERVER_NAME",
    "get_skill_agent_mcp_server",
]
