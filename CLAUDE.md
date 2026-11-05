# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A hub-and-spoke multi-agent system that extracts structured skill data from resumes and job postings. It exposes a small upload API, hands each document to a "coordinator" agent (Claude Agent SDK) that fans out to parallel MCP extraction tools, and checkpoints every step in Redis so work survives retries and process restarts. This repo is one of three:

- **talent_distiller_agent** (this repo) — upload API + coordinator orchestration.
- **mcp_skills_extractor_agents** (sibling repo) — the MCP server providing the 4 extraction tools (technical/soft skills, certifications, languages). Must be running locally for the coordinator to do anything.
- **labs-agent-lib** (sibling repo, installed as a dependency) — shared utilities: `get_logger`, `extract_text`, `file_writer`, agent settings/environment helpers. Treat it as external; don't reimplement its helpers here.

Full local setup (cloning siblings, Redis container, `.env`) is documented in `doc/how_run_as_development_mode.md`.

## Commands

```sh
# Install deps (uv is the primary tool; requirements.txt/requirements-dev.txt are generated from it)
uv sync

# Run the API + background poller (same process, see Architecture below)
uv run talent-distiller-agent-api

# Run the coordinator directly against one file (CLI entrypoint)
uv run python -m talent_distiller_agent.coordinators <path_to_resume_or_job_posting>

# Tests (coverage gate is 100%, see pyproject.toml)
uv run pytest
uv run pytest tests/coordinators/test_coordinator.py
uv run pytest tests/coordinators/test_coordinator.py::test_builds_options_queries_and_processes_the_stream_when_tools_are_allowed
```

The MCP server from `mcp_skills_extractor_agents` must be running (default `http://127.0.0.1:8000/mcp`) and Redis must be reachable for the app to function end-to-end; tests mock/fake both and don't need either running.

## Architecture

### Process shape

`api/app.py` builds a single Starlette app whose `lifespan` starts `main.start_process()` as a background `asyncio` task alongside the HTTP routes. The upload endpoints (`POST /resume`, `POST /job_posting`) only write the file to `resume_dir`/`job_posting_dir` on local disk; `main.py`'s poll loop (one loop per document type, both run concurrently via `asyncio.gather`) later picks it up. This is deliberate: API and processing share one process/pod so an uploaded file is always processed by the same pod that received it, with no shared filesystem needed across replicas — durability across retries instead comes from Redis.

### The coordinator turn (`coordinators/coordinator.py`)

Everything is parameterized by `DocumentType` (`RESUME` / `JOB_POSTING`) through a `CoordinatorSpec` lookup table (`COORDINATOR_SPECS`) rather than subclassing — the same code path handles both, picking a different system prompt and XML tag names. One call to `run_coordinator(file_path, doc_type)`:

1. Opens a `RedisJobStore` (the checkpoint state machine) and a `CoordinatorGuardrail` bound to it.
2. `guardrail.pre_execution_hook` decides what happens *before* spending any tokens: if all fields are already checkpointed, short-circuits straight to "processed"; if the per-file `revision_number` exceeds `coordinator_max_revision_number`, short-circuits to "failed"; otherwise returns the deduplicated list of MCP tool names still needed (derived from `JobStatus.missing_fields`).
3. If there's work to do, builds `ClaudeAgentOptions` with all 4 MCP server aliases (`mcp_client/skill_agent.py`), but constrains `allowed_tools` to only the ones actually needed this turn, and attaches a `PreToolUse` hook (`guardrail.build_sdk_hooks`).
4. Runs the agent turn and drains it with `message_stream_handler.process_coordinator_stream`.
5. `guardrail.post_execution_hook` persists session id/completion and routes the file to `processed/` or `failed/` via `labs_agent_lib.file_writer`.
6. Regardless of success/exception, always calls `tracker.unify_by_filename` and returns the unified result — a failed turn just means fewer fields got filled in; the next poll cycle retries only the missing ones.

### Redis as the resumability layer (`storage/redis_job_store.py`)

`RedisJobStore` is the single source of truth, keyed by lowercased filename (`resume_job:<name>` / `job_posting:<name>`). It's intentionally field-granular: each extraction domain (`technical_skills`, `soft_skills`, `certifications`, `languages`, plus `desirable_<field>` variants exclusive to job postings) is its own hash field, so a partially-successful turn leaves durable progress — only the fields still missing get retried on the next pass. `JobStatus.missing_fields` (computed fresh from Redis, not cached) is what both the guardrail and the agent prompt use to decide what to do next. `unify_by_filename` reconstructs the typed Pydantic result (`UnifiedResumeJob`, or `UnifiedJobPostingJob` which adds the four `desirable_*` fields) directly from the Redis hash, including any recorded `error:<field>` entries.

### Guardrails = the retry/safety contract (`guardrails/coordinator_guardrails.py`)

Three distinct enforcement points, not one:
- **`pre_execution_hook`** (before the agent runs): completion/failure short-circuits, revision counting, computing `allowed_tools`.
- **`PreToolUse` SDK hook** (while the agent runs): denies a tool call if the document's structured content isn't in Redis yet (polls briefly for it, since Phase 1/Phase 2 happen in the same turn) or if its target field was already checkpointed — this is what makes it safe for the model to (incorrectly) call a tool twice.
- **`post_execution_hook`** (after the stream ends): final completed/failed routing.

`FIELD_TO_MCP_TOOL` (built from the inverse of `EXTRACTION_TOOL_TO_FIELD`) is how a missing Redis field gets turned back into the MCP tool name that fills it.

### Prompts (`prompts/`)

Both orchestration prompts enforce the same strict two-phase protocol per turn: Phase 1 (only if raw content was supplied) reformat it into `<formatted_resume>`/`<formatted_job_posting>` tags with no fabrication; Phase 2 invoke every tool listed in `<pending_tools>` in parallel, in the same turn, then reply with the literal word `DONE`. No in-session retries — that's handled entirely outside the agent via `revision_number`.

### Stream handling (`coordinators/message_stream_handler.py`)

Consumes `client.receive_response()` and does the actual Redis writes: extracts `<formatted_*>` content from `TextBlock`s, and for each MCP `ToolUseBlock`/`ToolResultBlock` pair, resolves whether the result belongs under the plain field or the `desirable_` variant (job postings only — see `_resolve_target_field` / `_is_desirable_tool_input`), and persists it via `tracker.save_agent_result` or records an error via `save_agent_error`. Also handles the case where one tool call returns a single composite JSON containing both `mandatory`/`required` and `desirable` keys, splitting it into two Redis fields.

### MCP wiring (`mcp_client/skill_agent.py`)

Each of the 4 extraction tools gets its own MCP server alias/URL (`candidate-skill-agent-technical`, `-soft`, `-certifications`, `-languages`), all defaulting to the same single server. This lets `mcp_skills_extractor_agents` later split tools across independently-scaled deployments without any code change here — only a settings override. `EXTRACTION_TOOL_TO_FIELD` is the canonical tool-name → Redis-field map referenced by both the guardrails and the stream handler; add new entries here (and to `_TOOL_SPECS`) when a new extraction domain is introduced.

## Testing conventions

- Test tree mirrors `src/` 1:1 under `tests/`.
- Unit tests monkeypatch module-level names directly (e.g. `monkeypatch.setattr(coordinator_module, "RedisJobStore", ...)`) rather than using constructor injection or a mocking library; small hand-written `_Fake*` classes stand in for `ClaudeSDKClient`, `RedisJobStore`, and `CoordinatorGuardrail`. Follow this pattern — see `tests/coordinators/test_coordinator.py` for the reference shape.
- `fakeredis` backs the `RedisJobStore` tests instead of a real Redis instance.
- `pytest-asyncio` runs in `asyncio_mode = "auto"` — async test functions need no `@pytest.mark.asyncio` marker.
- Coverage is enforced at 100% (`fail_under = 100` in `pyproject.toml`); `src/talent_distiller_agent/coordinators/main.py` is explicitly excluded since it's a hand-edited manual dev entrypoint, not part of the tested surface.

## Settings

All app config is a `pydantic-settings` `Settings` model (`settings/settings.py`) reading `.env` with prefix `TALENT_DISTILLER_AGENT_` (separate from `labs-agent-lib`'s own `LABS_AGENT_LIB_` settings). `processed`/`failed` folder defaults are derived from `resume_dir`/`job_posting_dir` in a `model_validator`, not hardcoded. See the table in `doc/how_run_as_development_mode.md` for the full variable list — update that table when adding a new setting.
