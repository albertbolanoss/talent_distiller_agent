"""Mocked MCP tools for parallel resume extraction (Tech Skills, Soft Skills, Certifications, Languages)."""

import asyncio
import json
import os
from typing import Annotated, TypedDict

from claude_agent_sdk import ToolAnnotations, tool
from labs_agent_lib import get_logger

logger = get_logger(__name__)
MODULE = "[ExtractionMocks]"

# Set env var MOCK_FAIL_ONCE_FIELDS="certifications,languages" to simulate a crash on Attempt 1
_FAILED_ONCE_TRACKER: set[str] = set()


def _should_simulate_failure(field_name: str) -> bool:
    """Returns True on the first call if `field_name` is configured to fail once."""
    raw_targets = os.getenv("MOCK_FAIL_ONCE_FIELDS", "")
    targets = {t.strip() for t in raw_targets.split(",") if t.strip()}
    if field_name in targets and field_name not in _FAILED_ONCE_TRACKER:
        _FAILED_ONCE_TRACKER.add(field_name)
        return True
    return False


class ExtractionInput(TypedDict):
    resume_path: Annotated[str, "Path of the resume being processed."]


@tool(
    "extract_technical_skills",
    "Extracts technical skills, programming languages, frameworks, and cloud tools from the resume.",
    ExtractionInput,
    annotations=ToolAnnotations(read_only_hint=True),
)
async def extract_technical_skills(args: ExtractionInput) -> dict:
    logger.info("%s Running extract_technical_skills for %s", MODULE, args["resume_path"])
    await asyncio.sleep(0.4)

    if _should_simulate_failure("technical_skills"):
        return {
            "content": [{"type": "text", "text": "Simulated MCP timeout in tech-skills-agent"}],
            "is_error": True,
        }

    payload = {
        "languages": ["Python 3.12", "Java 21", "SQL"],
        "frameworks": ["Spring Boot 3.5", "FastMCP", "Pydantic V2"],
        "infrastructure": ["GKE Autopilot", "Apache Kafka", "Redis", "Docker"],
    }
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


@tool(
    "extract_soft_skills",
    "Extracts leadership, communication, and interpersonal soft skills from the resume.",
    ExtractionInput,
    annotations=ToolAnnotations(read_only_hint=True),
)
async def extract_soft_skills(args: ExtractionInput) -> dict:
    logger.info("%s Running extract_soft_skills for %s", MODULE, args["resume_path"])
    await asyncio.sleep(0.3)

    if _should_simulate_failure("soft_skills"):
        return {
            "content": [{"type": "text", "text": "Simulated MCP error in soft-skills-agent"}],
            "is_error": True,
        }

    payload = {
        "soft_skills": [
            "Technical Leadership",
            "Cross-functional Collaboration",
            "Mentoring",
            "Problem Solving",
        ]
    }
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


@tool(
    "extract_certifications",
    "Extracts professional certifications and credentials from the resume.",
    ExtractionInput,
    annotations=ToolAnnotations(read_only_hint=True),
)
async def extract_certifications(args: ExtractionInput) -> dict:
    logger.info("%s Running extract_certifications for %s", MODULE, args["resume_path"])
    await asyncio.sleep(0.5)

    if _should_simulate_failure("certifications"):
        return {
            "content": [{"type": "text", "text": "Simulated MCP connection drop in certs-agent"}],
            "is_error": True,
        }

    payload = {
        "certifications": [
            {"name": "Claude Certified Architect - Foundations", "issuer": "Anthropic", "status": "Active"},
            {"name": "SnowPro Core Certification", "issuer": "Snowflake", "status": "Active"},
        ]
    }
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


@tool(
    "extract_languages",
    "Extracts spoken/written human languages and proficiency levels from the resume.",
    ExtractionInput,
    annotations=ToolAnnotations(read_only_hint=True),
)
async def extract_languages(args: ExtractionInput) -> dict:
    logger.info("%s Running extract_languages for %s", MODULE, args["resume_path"])
    await asyncio.sleep(0.2)

    if _should_simulate_failure("languages"):
        return {
            "content": [{"type": "text", "text": "Simulated MCP crash in lang-agent"}],
            "is_error": True,
        }

    payload = {
        "languages": [
            {"language": "Spanish", "proficiency": "Native"},
            {"language": "English", "proficiency": "B2 - Upper Intermediate"},
        ]
    }
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}
