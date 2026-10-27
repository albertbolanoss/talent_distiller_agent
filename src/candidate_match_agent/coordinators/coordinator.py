"""Coordinator: delegates reading a resume document to the file-reader MCP tool with a 3-attempt quality evaluator."""

import re
import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from candidate_match_agent.agent_environment import get_agent_environment
from candidate_match_agent.libs import get_logger, get_settings
from candidate_match_agent.tools import FILE_READER_SERVER, FILE_READER_SERVER_NAME
from candidate_match_agent.prompts import DOCUMENT_EXTRACTION_PROMPT

from .message_stream_handler import process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"
MAX_QUALITY_ATTEMPTS = 3


def evaluate_extracted_text(text: str | None) -> tuple[bool, list[str]]:
    """Evaluates whether the reconstructed plain text meets structural and cleanliness criteria."""
    if not text or not text.strip():
        return False, ["The output is empty."]

    issues: list[str] = []
    cleaned = text.strip()
    non_empty_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    # 1. Minimum length sanity check
    if len(cleaned) < 100:
        issues.append("The extracted content is abnormally short (fewer than 100 characters).")

    # 2. Detect vertical word-per-line PDF fragmentation (e.g. >30% of lines have only 1 word)
    if len(non_empty_lines) > 15:
        single_word_lines = sum(1 for line in non_empty_lines if len(line.split()) == 1)
        if (single_word_lines / len(non_empty_lines)) > 0.30:
            issues.append(
                "Broken line-break artifacts detected: too many single-word lines. "
                "Merge fragmented lines into coherent sentences and bullet points."
            )

    # 3. Detect leftover non-breaking spaces (\xa0)
    if "\u00a0" in cleaned:
        issues.append("Non-breaking spaces (\\u00a0) detected. Normalize all whitespace to standard spaces.")

    # 4. Detect forbidden Markdown formatting
    if "```" in cleaned or "**" in cleaned or re.search(r"^#{1,6}\s", cleaned, re.MULTILINE):
        issues.append("Markdown syntax detected (headers, bolding, or code fences). Output must be strict plain text.")

    # 5. Detect conversational preamble
    preamble_patterns = (
        "here is the",
        "sure, here",
        "below is the",
        "i have extracted",
        "extracted text:",
    )
    first_line_lower = non_empty_lines[0].lower() if non_empty_lines else ""
    if any(first_line_lower.startswith(p) for p in preamble_patterns):
        issues.append("Conversational preamble detected. Start directly with the document's content.")

    return len(issues) == 0, issues


async def run_coordinator(model: str, resume_path: str) -> str | None:
    """Reads `resume_path` via the file-reader MCP tool, evaluates quality, and retries up to 3 times."""
    agent_env = get_agent_environment(get_settings())
    initial_prompt = f"<resume_path>{resume_path}</resume_path>"

    options = ClaudeAgentOptions(
        system_prompt=DOCUMENT_EXTRACTION_PROMPT,
        model=model,
        env=agent_env.env,
        setting_sources=[],
        mcp_servers={FILE_READER_SERVER_NAME: FILE_READER_SERVER},
        allowed_tools=["mcp__" + FILE_READER_SERVER_NAME + "__read_document"],
    )

    final_result: str | None = None

    async with ClaudeSDKClient(options=options) as client:
        logger.info("%s Starting coordinator for resume_path=%s", MODULE, resume_path)
        current_prompt = initial_prompt

        for attempt in range(1, MAX_QUALITY_ATTEMPTS + 1):
            logger.info("%s Execution attempt %d/%d", MODULE, attempt, MAX_QUALITY_ATTEMPTS)
            await client.query(current_prompt)
            final_result, stop_reason, session_id = await process_coordinator_stream(client)

            passed, issues = evaluate_extracted_text(final_result)
            if passed:
                logger.info(
                    "%s Quality evaluation passed on attempt %d/%d | stop_reason=%s | session_id=%s",
                    MODULE,
                    attempt,
                    MAX_QUALITY_ATTEMPTS,
                    stop_reason,
                    session_id,
                )
                break

            logger.warning(
                "%s Quality evaluation failed on attempt %d/%d | issues=%s",
                MODULE,
                attempt,
                MAX_QUALITY_ATTEMPTS,
                issues,
            )

            if attempt < MAX_QUALITY_ATTEMPTS:
                feedback_items = "\n".join(f"- {issue}" for issue in issues)
                current_prompt = (
                    f"Your previous output failed the Quality Evaluator (Attempt {attempt}/{MAX_QUALITY_ATTEMPTS}) "
                    f"for the following reasons:\n{feedback_items}\n\n"
                    "Reconstruct and return the complete document text fixing all listed issues. "
                    "If the raw extraction was incomplete, call `read_document` again. "
                    "Respond ONLY with the corrected plain text."
                )

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(final_result)
    return final_result