"""Tests for the HTTP MCP client config of the external candidate-skill-agent server(s)."""

from talent_distiller_agent.mcp_client import EXTRACTION_TOOL_TO_FIELD, get_skill_agent_mcp_servers
from talent_distiller_agent.settings import Settings


def test_extraction_tool_to_field_maps_every_remote_extraction_tool_under_its_own_alias():
    assert EXTRACTION_TOOL_TO_FIELD == {
        "mcp__candidate-skill-agent-technical__extract_technical_skills": "technical_skills",
        "mcp__candidate-skill-agent-soft__extract_soft_skills": "soft_skills",
        "mcp__candidate-skill-agent-certifications__extract_certifications": "certifications",
        "mcp__candidate-skill-agent-languages__extract_languages": "languages",
    }


def test_builds_one_http_mcp_server_entry_per_tool_defaulting_to_the_same_url():
    settings = Settings(_env_file=None)

    server_configs = get_skill_agent_mcp_servers(settings)

    assert server_configs == {
        "candidate-skill-agent-technical": {"type": "http", "url": "http://127.0.0.1:8000/mcp"},
        "candidate-skill-agent-soft": {"type": "http", "url": "http://127.0.0.1:8000/mcp"},
        "candidate-skill-agent-certifications": {"type": "http", "url": "http://127.0.0.1:8000/mcp"},
        "candidate-skill-agent-languages": {"type": "http", "url": "http://127.0.0.1:8000/mcp"},
    }


def test_each_tool_can_be_pointed_at_its_own_independent_server():
    settings = Settings(
        _env_file=None,
        skill_agent_technical_mcp_url="http://skill-agent-technical/mcp",
        skill_agent_soft_mcp_url="http://skill-agent-soft/mcp",
        skill_agent_certifications_mcp_url="http://skill-agent-certifications/mcp",
        skill_agent_languages_mcp_url="http://skill-agent-languages/mcp",
    )

    assert get_skill_agent_mcp_servers(settings) == {
        "candidate-skill-agent-technical": {"type": "http", "url": "http://skill-agent-technical/mcp"},
        "candidate-skill-agent-soft": {"type": "http", "url": "http://skill-agent-soft/mcp"},
        "candidate-skill-agent-certifications": {
            "type": "http",
            "url": "http://skill-agent-certifications/mcp",
        },
        "candidate-skill-agent-languages": {"type": "http", "url": "http://skill-agent-languages/mcp"},
    }
