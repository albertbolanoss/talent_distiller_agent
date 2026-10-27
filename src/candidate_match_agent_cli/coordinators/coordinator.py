"""Coordinator: delegates reading a resume document to the file-reader MCP tool."""

import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from labs_agent_lib import get_logger, get_settings, get_agent_environment
from candidate_match_agent_cli.tools import FILE_READER_SERVER, FILE_READER_SERVER_NAME
from candidate_match_agent_cli.prompts import DOCUMENT_READ_PROMPT

from .message_stream_handler import process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"


async def run_coordinator(model: str, resume_path: str) -> dict:
    """Reads `resume_path` via the file-reader MCP tool and returns its path and content."""
    agent_env = get_agent_environment(get_settings())
    prompt = f"<resume_path>{resume_path}</resume_path>"

    options = ClaudeAgentOptions(
        system_prompt=DOCUMENT_READ_PROMPT,
        model=model,
        env=agent_env.env,
        setting_sources=[],
        mcp_servers={FILE_READER_SERVER_NAME: FILE_READER_SERVER},
        allowed_tools=["mcp__" + FILE_READER_SERVER_NAME + "__read_document"],
    )

    async with ClaudeSDKClient(options=options) as client:
        logger.info("%s Reading resume_path=%s", MODULE, resume_path)
        await client.query(prompt)
        content, stop_reason, session_id = await process_coordinator_stream(client)
        logger.info(
            "%s Finished reading resume_path=%s | stop_reason=%s | session_id=%s",
            MODULE, resume_path, stop_reason, session_id,
        )

    result = {"resume_path": resume_path, "content": content}
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    return result
