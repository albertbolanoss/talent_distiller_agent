"""MCP client wiring for the external candidate-skill-agent HTTP server(s)."""

from .skill_agent import EXTRACTION_TOOL_TO_FIELD, get_skill_agent_mcp_servers

__all__ = [
    "EXTRACTION_TOOL_TO_FIELD",
    "get_skill_agent_mcp_servers",
]
