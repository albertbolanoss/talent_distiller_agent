"""Minimal coordinator: delegates reading a resume document to the file-reader MCP tool."""

import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from candidate_match_agent.agent_environment import get_agent_environment
from candidate_match_agent.libs import get_logger, get_settings
from candidate_match_agent.tools import FILE_READER_SERVER, FILE_READER_SERVER_NAME

from .message_stream_handler import process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"

COORDINATOR_PROMPT = """### Role
You are a document-reading assistant.

### Objective
You will receive the path to a resume document inside `<resume_path>`. Call the
`read_document` tool with that path to obtain the document's raw text content.

### Output
Respond with exactly the text content returned by the tool - no extra commentary,
no markdown formatting, nothing added or removed."""


async def run_coordinator(model: str, resume_path: str) -> str | None:
    """Reads `resume_path` via the file-reader MCP tool and prints its raw content."""
    agent_env = get_agent_environment(get_settings())
    user_prompt = f"<resume_path>{resume_path}</resume_path>"

    options = ClaudeAgentOptions(
        system_prompt=COORDINATOR_PROMPT,
        model=model,
        env=agent_env.env,
        setting_sources=[],
        mcp_servers={FILE_READER_SERVER_NAME: FILE_READER_SERVER},
        allowed_tools=["mcp__" + FILE_READER_SERVER_NAME + "__read_document"],
    )

    async with ClaudeSDKClient(options=options) as client:
        logger.info("%s Starting coordinator for resume_path=%s", MODULE, resume_path)
        await client.query(user_prompt)
        final_result, stop_reason, session_id = await process_coordinator_stream(client)
        logger.info(
            "%s Finished coordinator | stop_reason=%s | session_id=%s", MODULE, stop_reason, session_id
        )

    # stdout's legacy encoding (e.g. cp1252 on Windows terminals) can't represent
    # every character a resume may contain (bullets, accents, ...); reconfigure it
    # to UTF-8 so printing never crashes on them.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(final_result)
    return final_result
