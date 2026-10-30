"""HTTP MCP client wiring for the external candidate-skill-agent server."""

from claude_agent_sdk.types import McpHttpServerConfig

from candidate_match_agent_cli.settings import Settings

SKILL_AGENT_SERVER_NAME = "candidate-skill-agent"

READ_DOCUMENT_TOOL_NAME = f"mcp__{SKILL_AGENT_SERVER_NAME}__read_document"

# Map each remote MCP extraction tool name to its Redis Hash field name
EXTRACTION_TOOL_TO_FIELD: dict[str, str] = {
    f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_technical_skills": "technical_skills",
    f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_soft_skills": "soft_skills",
    f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_certifications": "certifications",
    f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_languages": "languages",
}


def get_skill_agent_mcp_server(settings: Settings) -> McpHttpServerConfig:
    """Builds the streamable-HTTP MCP server config for the candidate-skill-agent server."""
    return {"type": "http", "url": settings.skill_agent_mcp_url}
