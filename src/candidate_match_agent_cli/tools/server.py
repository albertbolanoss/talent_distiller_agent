"""In-process MCP server exposing this agent's document tools."""

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server

from .file_reader import read_document

FILE_READER_SERVER_NAME = "file-reader"

FILE_READER_SERVER: McpSdkServerConfig = create_sdk_mcp_server(
    name=FILE_READER_SERVER_NAME,
    tools=[read_document],
)
