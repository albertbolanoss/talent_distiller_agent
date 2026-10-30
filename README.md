# candidate-match-agent-cli

This AI agent analyzes job postings against resumes to identify matching skills and rank candidates.

This agent's shared utilities (settings, logging, document text extraction, agent environment) live in their own
sibling repo, `labs-agent-lib`, and are consumed here as a regular dependency (see `labs-agent-lib` in
`[project.dependencies]` and the `[tool.uv.sources]` override in `pyproject.toml`). During local development it
resolves to `../labs-agent-lib` on disk, so that repo needs to be checked out as a sibling of this one (same
parent folder).

Once `labs-agent-lib` is published to PyPI, the path override in `[tool.uv.sources]` can be dropped so `uv.lock`
pins a released version instead of the local checkout.

The 5 resume-extraction tools (`read_document`, `extract_technical_skills`, `extract_soft_skills`,
`extract_certifications`, `extract_languages`) are **not** implemented in this repo. They're served by the
sibling [`candidate-skill-agent`](https://github.com/albertbolanoss/candidate-skill-agent) MCP server, which the
coordinator connects to as a remote streamable-HTTP MCP client — see
[Connecting to the candidate-skill-agent MCP server](#connecting-to-the-candidate-skill-agent-mcp-server) below.

## Prerequisites.

- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## How to install dependencies

1. Clone the repo (or download and unzip it):

   ```bash
   git clone https://github.com/albertbolanoss/candidate-match-agent-cli.git
   cd candidate-match-agent-cli
   ```

2. Sync the environment (installs the exact dependency versions pinned in `uv.lock`):

   ```bash
   uv sync
   ```

## Configuring the .env file

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `CANDIDATE_MATCH_AGENT_PROVIDER` | Gateway to route through: `portkey` (default) or `anthropic`. |
| `CANDIDATE_MATCH_AGENT_LOG_LEVEL` | Log verbosity: `DEBUG`, `INFO` (default), `WARNING`, or `ERROR`. |
| `CANDIDATE_MATCH_AGENT_PORTKEY_API_KEY` | Portkey workspace key. Required when `PROVIDER=portkey`. Ask your AI Academy facilitator for one. |
| `CANDIDATE_MATCH_AGENT_ANTHROPIC_API_KEY` | Direct Anthropic API key. Required only when `PROVIDER=anthropic`. |
| `CANDIDATE_MATCH_AGENT_SKILL_AGENT_MCP_URL` | URL of the `candidate-skill-agent` MCP server (streamable HTTP, must end in `/mcp`). Defaults to `http://127.0.0.1:8000/mcp`. |

`.env` is gitignored — never commit it. Not in `.env.example` because it's not required, but if your Portkey
workspace routes through a specific provider/credential alias, set it locally with:

```bash
CANDIDATE_MATCH_AGENT_PORTKEY_VIRTUAL=aws-bedrock-use2
```

(It's not a secret — just an identifier — so it's read as a plain setting, not through the Secret in the
Helm chart.)

## Connecting to the candidate-skill-agent MCP server

The coordinator (`candidate_match_agent_cli.coordinators.coordinator`) talks to the 5 resume-extraction tools over
a **streamable HTTP MCP client** (see `src/candidate_match_agent_cli/mcp_client/skill_agent.py`), pointed at the
URL in `CANDIDATE_MATCH_AGENT_SKILL_AGENT_MCP_URL` (defaults to `http://127.0.0.1:8000/mcp`). That server lives in
the sibling `candidate-skill-agent` repo and must be running before you start this project's coordinator/API.

1. Clone `candidate-skill-agent` as a sibling of this repo (same parent folder) and `uv sync` it.
2. Start it over the `http` transport, on the host/port matching your `.env`:

   ```bash
   uv run python -m candidate_skill_agent.main --protocol http --host 127.0.0.1 --port 8000
   ```

3. Run this project as usual (see below) - the coordinator will connect to
   `http://127.0.0.1:8000/mcp` on its next resume-processing turn.

See that repo's `SETUP.md` for other transports (`stdio`, `sse`) and debugging with the MCP Inspector.

## How to run this project

```bash
uv run candidate-match-agent-api
```

This serves the resume-upload API and runs the background resume-processing loop in the same
process - see [Resume-upload API](#resume-upload-api) below.

## How to run the tests

Tests live under `tests/` and use `pytest` + `pytest-cov`. `uv sync` already installs them as dev dependencies.

```bash
uv run pytest
```

This also prints a coverage report for `src/candidate_match_agent_cli` (configured in `pyproject.toml`); a line is only "covered" if a test actually executes it, and `Missing` lists any line numbers that aren't.

`labs-agent-lib` has its own repo, `pyproject.toml`, and test suite with a 100% coverage gate — see
`../labs-agent-lib/README.md` and `../labs-agent-lib/PUBLISHING.md`.


uv run python -m candidate_match_agent_cli.coordinators "us.anthropic.claude-sonnet-5" "resume/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf"

## Resume-upload API

`candidate-match-agent-api` is the only entrypoint: on startup it starts the background
resume-processing loop (`process_resumes`, in `main.py`) as a task tied to the app's lifespan,
and serves an HTTP API with an endpoint to upload resumes into the polled directory:

```bash
uv run candidate-match-agent-api
```

| Method & path  | Description |
|---|---|
| `GET /healthz` | Liveness/readiness probe. |
| `POST /resumes` | Multipart upload (field name `file`) that saves a resume into `resume_dir`. Rejects unsupported extensions; the background loop picks the file up on its next poll. |

```bash
curl -F "file=@input/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf" http://localhost:8080/resumes
```

The port defaults to `8080` and is read directly from the `PORT` env var (see `.env.example`).

## Deploy in Kubernetes cluster

Follow this [guide](helm/candidate-match-agent-cli/README.md) to deploy this application in kubernetes cluster or Minikube using Helm Chart.