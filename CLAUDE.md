# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`talent_distiller_agent` is the orchestration service of a hub-and-spoke multi-agent
system that extracts structured skill data (technical skills, soft skills,
certifications, languages, seniority) from resumes and job postings. This repo exposes
the upload API and the Coordinator agent (the "hub"). The actual extraction logic lives
in a sibling repo and is called over MCP (the "spokes"):

- **`mcp_skills_extractor_agents`** (sibling repo) — MCP server exposing the 4 extraction
  sub-agents as tools.
- **`labs-agent-lib`** (sibling repo, published as a package) — shared utilities used
  throughout this repo: `get_logger`, `extract_text`, `file_writer`,
  `get_agent_settings`/`get_agent_environment`, `file_reader.SUPPORTED_EXTENSIONS`.

Both are expected to be cloned as sibling directories during local development (see
README "Project Repositories"), and the MCP server must be running for the Coordinator
to do anything useful.

## Commands

```sh
# Install deps (uv is the primary tool; requirements.txt is kept in sync for pip users)
uv sync

# Run the app (also requires a running Redis instance and the sibling MCP server)
uv run talent-distiller-agent-api

# Run all tests
uv run pytest

# Run a single test file / test
uv run pytest tests/coordinators/test_coordinator.py
uv run pytest tests/coordinators/test_coordinator.py::test_name -v
```

Coverage is enforced at **100%** (`fail_under = 100` in `pyproject.toml`, scoped to
`src/talent_distiller_agent`, branch coverage on). `uv run pytest` always runs with
`--cov`; a change that drops coverage below 100% fails the test run, not just a separate
lint step. The only exclusion is `coordinators/main.py` (a manual dev entrypoint) and
`if __name__ == "__main__":` guards.

Tests mock Redis with `fakeredis` (see `requirements-dev.txt` / the `dev` dependency
group) rather than hitting a real server — there is no `conftest.py`; fixtures are set up
per test file.

## Architecture

### Two processes in one, per pod

`api/app.py`'s Starlette `lifespan` starts `main.start_process()` as a background
`asyncio` task alongside the HTTP routes, in the **same process**. This is deliberate:
a document uploaded to a given pod is picked up by that same pod's poll loop, with no
shared work queue needed across replicas. There are two polling loops running
concurrently (`main.process_only_resumes` / `process_job_postings`), each scanning its
own directory (`resume_dir` / `job_posting_dir`) on its own interval and batch size, and
invoking `run_coordinator` per file found.

### The Coordinator turn (`coordinators/coordinator.py`)

`run_coordinator(file_path, doc_type)` is the central function. Resume and job-posting
processing share this one code path, differentiated only by a `CoordinatorSpec`
(`COORDINATOR_SPECS` dict) carrying the system prompt, XML tag names, etc. per
`DocumentType`. Per invocation it:

1. Opens a `RedisJobStore` for that file (checkpoint state keyed by filename — see
   below) and asks `CoordinatorGuardrail.pre_execution_hook` which MCP tools are still
   needed.
2. Builds a prompt from `<resume_path>`/`<job_posting_path>`, `<correlation_id>`, and
   (if content hasn't been checkpointed yet) the raw extracted text, then opens a
   `ClaudeSDKClient` with that document type's orchestration system prompt, the 4 MCP
   server configs, `allowed_tools` restricted to the still-missing fields, and a
   `PreToolUse` SDK hook from the guardrail.
3. Streams the turn through `process_coordinator_stream`
   (`coordinators/message_stream_handler.py`), which checkpoints both the
   structured document content and every tool result into Redis as they arrive.
4. Runs `CoordinatorGuardrail.post_execution_hook` to decide completed/failed, then
   reads back the unified Redis state and returns it.

This whole flow is wrapped in try/except so a single file's failure doesn't crash the
poll loop; the file just stays un-moved and gets retried on the next poll (up to the
revision cap below).

### Resilience: revision counter + idempotent fan-out, not retries-in-session

The system prompts (`prompts/resume_orchestration.py`,
`prompts/job_posting_orchestration.py`) explicitly forbid the model from retrying failed
tool calls itself — "state tracking and retries are managed externally." Retrying is an
**outer loop**: each poll of a not-yet-completed file increments
`revision_number` in Redis (`CoordinatorGuardrail.pre_execution_hook` →
`tracker.increment_attempts`) and only asks for the fields still missing
(`allowed_tools` is derived from `status.missing_fields`, deduplicated via
`FIELD_TO_MCP_TOOL`). Once `revision_number` exceeds
`coordinator_max_revision_number` (default 3), the file is moved to the
`failed`/`<doc>/failed` folder via `labs_agent_lib.file_writer` instead of being retried
again. On success it's moved to the `processed` folder. This means a crash mid-run loses
no completed fields — only the still-missing ones are re-requested next poll.

A second guardrail layer is the **`PreToolUse` SDK hook**
(`CoordinatorGuardrail.build_sdk_hooks`), which runs *inside* a turn, right before each
extraction tool call: it denies the call if the document's content isn't checkpointed in
Redis yet (with a short retry-wait loop, since content is saved from a separate assistant
text block the model may emit before or interleaved with tool calls), or if every Redis
field that tool would write to is already filled — preventing duplicate/wasted calls
within a single turn.

### Redis as the only state store (`storage/redis_job_store.py`)

`RedisJobStore` is keyed by `{resume_job:|job_posting:}{lowercased filename}` with a 24h
TTL. One `dataclass` (`DocumentStorageSpec`, in `STORAGE_SPECS`) per `DocumentType`
describes which fields that type tracks and which Pydantic model
(`UnifiedResumeJob` / `UnifiedJobPostingJob`) validates the final unified record.
Job postings track 8 extraction fields instead of 4: every mandatory field
(`ExtractionField`) has a `desirable_`-prefixed counterpart (`DesirableExtractionField`),
since a job posting distinguishes required vs. nice-to-have skills — resumes don't have
this distinction. `JobStatus.is_completed` (content present + no missing fields) is the
single source of truth for whether a file is done; nothing is computed from the
filesystem.

### Mandatory vs. desirable field resolution is a runtime heuristic

The 4 MCP extraction tools are the same regardless of document type (there's no separate
"desirable skill" tool). For job postings, `message_stream_handler._resolve_target_field`
decides at the moment a tool call happens whether its result belongs in the mandatory or
`desirable_` Redis field: it checks the tool call's own input for desirability markers
(`_is_desirable_tool_input`), then falls back to "mandatory if still missing and not yet
claimed this turn, otherwise desirable." `_save_tool_output` additionally handles the
case where a single tool call returns one JSON object containing both
`mandatory`/`required` and `desirable` keys, splitting it into two Redis writes.

### MCP wiring (`mcp_client/skill_agent.py`)

Each of the 4 extraction tools gets its **own** MCP server alias
(`candidate-skill-agent-{technical,soft,certifications,languages}`), all defaulting to
the same URL (`http://127.0.0.1:8000/mcp`) but independently overridable — the sibling
`mcp_skills_extractor_agents` service can be split into one deployment per tool via its
own `CANDIDATE_SKILL_AGENT_ACTIVE_TOOLS` setting without any code change here.
`EXTRACTION_TOOL_TO_FIELD` is the module-level map from the (namespaced) MCP tool name to
the base Redis field — it's the thing both the guardrail and the stream handler key off
of to know what a given tool call is for.

### Cross-service correlation for observability

`documentation/prompt_log_and_agent_transcript.md` is the detailed spec; the essential
fact to know when touching the Coordinator or storage layer: a `correlation_id` is minted
**once per file** in `RedisJobStore.init_or_get_state` (not per turn/revision) and reused
across every retry. It's threaded into the prompt as `<correlation_id>`, and the
orchestration prompts instruct the model to pass it as an explicit tool argument on every
extraction call, because there's no other way to tie a Coordinator run to the MCP-side
sub-agent calls it triggers (the SDK's own `session_id` isn't known until the turn ends,
and the actual HTTP call to the MCP server is made by the `claude` CLI subprocess, not
this repo's Python). `observability/prompt_log.py` and `observability/agent_transcript.py`
both write JSONL keyed by this id under `documentation/prompt_log/` and
`documentation/agent_transcript/` (gitignored except for one committed sample file), and
can be globally disabled via `TALENT_DISTILLER_AGENT_OBSERVABILITY_ENABLED=false`.

### Settings

All configuration is a single `pydantic-settings` `Settings` class
(`settings/settings.py`), env-prefixed `TALENT_DISTILLER_AGENT_`, loaded from `.env` and
cached via `lru_cache` (`get_settings()`). Processed/failed folder settings default to a
subfolder of their respective `*_dir` via a `model_validator` if left unset — don't
hardcode `"resume/processed"` elsewhere; read `settings.coordinator_processed_folder` (or
the guardrail's `processed_folder`/`failed_folder` properties, which already apply this
same default resolution per `DocumentType`). See the README's env var table for the full
list and defaults.

### Requirements

Python 3.14+. `uv` is the primary/recommended tool; `requirements.txt`/`requirements-dev.txt`
are uv-exported mirrors for plain-pip workflows, not maintained by hand.
