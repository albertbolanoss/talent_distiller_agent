"""Tests for the HTTP MCP client config of the external candidate-skill-agent server."""

from candidate_match_agent_cli.mcp_client import (
    EXTRACTION_TOOL_TO_FIELD,
    READ_DOCUMENT_TOOL_NAME,
    SKILL_AGENT_SERVER_NAME,
    get_skill_agent_mcp_server,
)
from candidate_match_agent_cli.settings import Settings


def test_read_document_tool_name_is_namespaced_under_the_skill_agent_server():
    assert READ_DOCUMENT_TOOL_NAME == f"mcp__{SKILL_AGENT_SERVER_NAME}__read_document"


def test_extraction_tool_to_field_maps_every_remote_extraction_tool():
    assert EXTRACTION_TOOL_TO_FIELD == {
        f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_technical_skills": "technical_skills",
        f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_soft_skills": "soft_skills",
        f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_certifications": "certifications",
        f"mcp__{SKILL_AGENT_SERVER_NAME}__extract_languages": "languages",
    }


def test_builds_an_http_mcp_server_config_from_settings():
    settings = Settings(_env_file=None, skill_agent_mcp_url="http://example.test/mcp")

    server_config = get_skill_agent_mcp_server(settings)

    assert server_config == {"type": "http", "url": "http://example.test/mcp"}
