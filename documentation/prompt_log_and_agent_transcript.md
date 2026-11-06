# Prompt Log & Agent Transcript

This document explains the observability feature added to **both**
`talent_distiller_agent` (this repo, the Coordinator) and `mcp-skills-extractor-agents`
(the sibling MCP server exposing the 4 extraction sub-agents). It is one feature
implemented twice, as a complementary pair, so a single file-processing run can be
reconstructed end-to-end across both services.

## 1. Two concepts, not one

| | Prompt Log | Agent Transcript |
|---|---|---|
| **Answers** | "What did we ask the model, and when?" | "What actually happened in this conversation, step by step?" |
| **Shape** | One flat line per outbound LLM call attempt | One ordered sequence of events per agent session |
| **Good for** | Fast search/filter across many runs ("show me every prompt sent in the last hour") | Replaying a single run end-to-end to debug *why* it produced a given result |
| **File** | `documentation/prompt_log/{correlation_id}.jsonl` | `documentation/agent_transcript/{correlation_id}.jsonl` |

They're deliberately separate files with a shared schema, not one merged log: the prompt
log stays small and greppable (it never repeats the full system prompt or every
assistant/tool-call detail), while the transcript is the rich record you open when you
already know *which* run you care about.

Neither existed before this change. Previously, both services only emitted plain,
leveled `logging` output via `labs_agent_lib.get_logger` (operational breadcrumbs:
"dispatching tool X", "attempt 2/3 failed") - useful for watching a live pod, but not an
audit trail of what was actually sent to or returned by the LLM, and nothing tied a
Coordinator run to the sub-agent calls it triggered on the other service.

## 2. Why this matters

- **Debugging a bad extraction.** When a resume comes out with the wrong seniority
  level or a missing skill, the transcript shows exactly what text was sent to the
  model and what it replied with - no need to reproduce the bug live against a real
  LLM.
- **Audit / compliance.** Resumes and job postings carry candidate PII. Knowing
  precisely what was sent to a third-party model gateway (Portkey/Anthropic) for a
  given file is a reasonable compliance ask, not a hypothetical one.
- **Reproducing self-correction loops.** Each extraction sub-agent retries up to
  `max_retries` times on invalid JSON. The transcript's `retry` events capture the exact
  validation error that triggered each follow-up turn.
- **Onboarding.** A new engineer can read one `correlation_id`'s transcript files across
  both repos and see the whole hub-and-spoke flow for a single file, turn by turn,
  instead of reverse-engineering it from code.

## 3. Correlation across two services

**The constraint:** the real Claude Agent SDK `session_id` is only known *after* a turn
finishes (`ResultMessage`), and this repo's Python code never makes the MCP HTTP call
itself - the `claude` CLI subprocess the SDK manages does. So there's no hook to inject
a trace id into that request from here.

**The fix:** a `correlation_id` (`uuid4().hex`) is minted **once per file-processing
job**, in `RedisJobStore.init_or_get_state` (`src/talent_distiller_agent/storage/redis_job_store.py`),
and reused across every revision/retry of that same file (same 24h TTL as the rest of
the job's checkpoint state). The Coordinator:

1. Reads it off `JobStatus.correlation_id` and adds it to the prompt as
   `<correlation_id>...</correlation_id>`, alongside the existing `<resume_path>` /
   `<job_posting_path>` tag (`coordinators/coordinator.py`).
2. The orchestration system prompts (`prompts/resume_orchestration.py`,
   `prompts/job_posting_orchestration.py`) instruct the model to pass that same value as
   the `correlation_id` argument on **every** extraction tool call.
3. `mcp-skills-extractor-agents`' 4 extraction tools accept that `correlation_id` and
   use it to key their own prompt-log/transcript files, with the same JSONL shape.

```
1 resume  ->  1 correlation_id
              |
              +-- documentation/agent_transcript/{correlation_id}.jsonl          (this repo: 1 Coordinator session)
              +-- documentation/agent_transcript/{correlation_id}__extract_technical_skills.jsonl   (sibling repo)
              +-- documentation/agent_transcript/{correlation_id}__extract_soft_skills.jsonl        (sibling repo)
              +-- documentation/agent_transcript/{correlation_id}__extract_certifications.jsonl     (sibling repo)
              +-- documentation/agent_transcript/{correlation_id}__extract_languages.jsonl          (sibling repo)
```

Each side still records its *own* Claude `session_id` once known (as the `session_id`
field on `session_end` events) - it's just not usable as the id that ties the two
services together, since it doesn't exist yet when the cross-service call happens.

This extends the existing `documentation/design/end_to_end_sequence.mmd` diagram: every
step in that sequence now also has a corresponding JSONL event in one of these files.

## 4. JSONL schema

Both files share an envelope:

```json
{"timestamp": "2026-01-15T10:03:21.558+00:00", "correlation_id": "9f1c...", "service": "talent_distiller_agent", "agent": "coordinator", "session_id": null, "event": "..."}
```

**Prompt log** - one `"event": "prompt"` line per outbound LLM call attempt:

```json
{"timestamp": "...", "correlation_id": "9f1c...", "service": "talent_distiller_agent", "agent": "coordinator", "event": "prompt", "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0", "system_prompt_name": "resume_coordinator_orchestration", "user_prompt": "<resume_path>resume/jane.pdf</resume_path>\n<correlation_id>9f1c...</correlation_id>\n...", "attempt": 1}
```

**Agent transcript** - one line per step, `event` is one of:

| `event` | When | Key fields |
|---|---|---|
| `session_start` | Once, right before the first `client.query(...)` | `model`, `system_prompt` (logged once, not repeated), `user_prompt`, `allowed_tools` |
| `assistant_text` | Every `TextBlock` the model emits | `text` |
| `tool_use` | Every tool call the model dispatches | `tool_use_id`, `tool_name`, `target_field`, `tool_input` |
| `tool_result` | Every tool result that comes back | `tool_use_id`, `tool_name`, `target_field`, `is_error`, `output` |
| `session_end` | Once, when the turn's `ResultMessage` arrives | `session_id`, `stop_reason`, `is_error` |

Source: the two writer classes (`PromptLogWriter`, `AgentTranscriptWriter`) live in
`labs_agent_lib.observability` (`labs-agent-lib`, the shared package, not this repo) -
they're **centralized there** because `mcp-skills-extractor-agents` needs the exact same
JSONL mechanics and event schema, just keyed one file per `{correlation_id}__{tool_name}`
instead of one per `{correlation_id}` (see that repo's own
`documentation/prompt_log_and_agent_transcript.md` for why). Each project still supplies
its *own* settings object (`Settings.observability_enabled`/`prompt_log_dir`/
`agent_transcript_dir`) and a `service` name at construction time - nothing about the
`TALENT_DISTILLER_AGENT_*` env vars moved. This repo constructs them in
`coordinators/coordinator.py` (`PromptLogWriter(settings, service="talent_distiller_agent")`,
`AgentTranscriptWriter(settings, service="talent_distiller_agent")`) and wires the calls
into `coordinators/coordinator.py` and `coordinators/message_stream_handler.py`
(`process_coordinator_stream`) at the exact points that already logged these events via
`labs_agent_lib.get_logger` - this feature adds a structured, durable line next to each
existing log statement, it doesn't replace the logging.

## 5. Where files live, and PII handling

Both directories are **gitignored** (`documentation/prompt_log/*.jsonl`,
`documentation/agent_transcript/*.jsonl` in `.gitignore`) - only a `.gitkeep`
placeholder is committed. Real resumes and job postings contain personal data, and these
files can contain their full text, so they must never be committed or shared outside the
environment that produced them.

## 6. Configuration

| Setting (`TALENT_DISTILLER_AGENT_` prefix) | Default | Purpose |
|---|---|---|
| `OBSERVABILITY_ENABLED` | `true` | Master on/off switch for both writers. |
| `PROMPT_LOG_DIR` | `documentation/prompt_log` | Where prompt-log JSONL files are written. |
| `AGENT_TRANSCRIPT_DIR` | `documentation/agent_transcript` | Where transcript JSONL files are written. |

(`mcp-skills-extractor-agents` exposes the equivalent three settings under its own
`CANDIDATE_SKILL_AGENT_` prefix.)

## 7. Known limitation

Both services run as horizontally scaled, independently deployed Kubernetes pods
(see `documentation/design/talent_distiller_agent_architecture.mmd` /
`mcp_skills_extractor_agents_architecture.mmd`) with pod-local, ephemeral storage. This
feature is file-based by design for local/dev-mode observability and to establish the
schema and `correlation_id` contract between the two services. Shipping these events to
a persistent or centralized sink (e.g. a mounted volume, an object store, or an
OpenTelemetry/log-aggregation backend) is future work, not implemented here.

## 8. Depending on `labs-agent-lib`

`labs-agent-lib>=0.1.0` (the real, production PyPI release - independently versioned
from its TestPyPI history, which already had this same observability module at `0.5.0`)
is required; earlier real-PyPI releases don't exist, since `0.1.0` was its first
production publish. No `[tool.uv.sources]` override is needed - `pyproject.toml`
resolves it from the default index. The `testpypi` index entry is kept only for testing
future prereleases there before cutting a real release.
