"""HTTP MCP client wiring for the external candidate-skill-agent server(s)."""

from claude_agent_sdk.types import McpHttpServerConfig

from talent_distiller_agent.settings import Settings

# One server alias per extraction tool, paired with the Settings field that resolves its URL
# and the Redis field it writes to. All four default to the same URL (a single do-everything
# server), but each can be pointed at its own deployment independently - e.g. when
# mcp-skills-extractor-agents' tools are split across one release per tool via
# CANDIDATE_SKILL_AGENT_ACTIVE_TOOLS.
_TOOL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("technical", "extract_technical_skills", "technical_skills"),
    ("soft", "extract_soft_skills", "soft_skills"),
    ("certifications", "extract_certifications", "certifications"),
    ("languages", "extract_languages", "languages"),
)

_TOOL_KEYS: tuple[str, ...] = tuple(key for key, _tool, _field in _TOOL_SPECS)

EXTRACTION_TOOL_TO_FIELD: dict[str, str] = {
    f"mcp__candidate-skill-agent-{key}__{tool}": field for key, tool, field in _TOOL_SPECS
}


def get_skill_agent_mcp_servers(settings: Settings) -> dict[str, McpHttpServerConfig]:
    """Builds one streamable-HTTP MCP server entry per extraction tool.

    Each entry's URL comes from `settings.skill_agent_<tool>_mcp_url`, which defaults to the
    same single-server URL for every tool.
    """
    return {
        f"candidate-skill-agent-{key}": {
            "type": "http",
            "url": getattr(settings, f"skill_agent_{key}_mcp_url"),
        }
        for key in _TOOL_KEYS
    }
