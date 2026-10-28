"""In-process MCP servers exposing document reading and parallel extraction tools."""

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server

from .file_reader import read_document
from .extraction_mocks import (
    extract_certifications,
    extract_languages,
    extract_soft_skills,
    extract_technical_skills,
)

FILE_READER_SERVER_NAME = "file-reader"
TECH_SKILLS_SERVER_NAME = "tech-skills-agent"
SOFT_SKILLS_SERVER_NAME = "soft-skills-agent"
CERTS_SERVER_NAME = "certs-agent"
LANG_SERVER_NAME = "lang-agent"

FILE_READER_SERVER: McpSdkServerConfig = create_sdk_mcp_server(
    name=FILE_READER_SERVER_NAME,
    tools=[read_document],
)

TECH_SKILLS_SERVER: McpSdkServerConfig = create_sdk_mcp_server(
    name=TECH_SKILLS_SERVER_NAME,
    tools=[extract_technical_skills],
)

SOFT_SKILLS_SERVER: McpSdkServerConfig = create_sdk_mcp_server(
    name=SOFT_SKILLS_SERVER_NAME,
    tools=[extract_soft_skills],
)

CERTS_SERVER: McpSdkServerConfig = create_sdk_mcp_server(
    name=CERTS_SERVER_NAME,
    tools=[extract_certifications],
)

LANG_SERVER: McpSdkServerConfig = create_sdk_mcp_server(
    name=LANG_SERVER_NAME,
    tools=[extract_languages],
)

__all__ = [
    "FILE_READER_SERVER_NAME",
    "TECH_SKILLS_SERVER_NAME",
    "SOFT_SKILLS_SERVER_NAME",
    "CERTS_SERVER_NAME",
    "LANG_SERVER_NAME",
    "FILE_READER_SERVER",
    "TECH_SKILLS_SERVER",
    "SOFT_SKILLS_SERVER",
    "CERTS_SERVER",
    "LANG_SERVER",
]
