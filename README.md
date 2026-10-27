# candidate-match-agent-cli

This AI agent analyzes job postings against resumes to identify matching skills and rank candidates.

This agent's shared utilities (settings, logging, document text extraction, agent environment) live in their own
sibling repo, `labs-agent-lib`, and are consumed here as a regular dependency (see `labs-agent-lib` in
`[project.dependencies]` and the `[tool.uv.sources]` override in `pyproject.toml`). During local development it
resolves to `../labs-agent-lib` on disk, so that repo needs to be checked out as a sibling of this one (same
parent folder).

Once `labs-agent-lib` is published to PyPI, the path override in `[tool.uv.sources]` can be dropped so `uv.lock`
pins a released version instead of the local checkout.

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
| `CANDIDATE_MATCH_AGENT_PORTKEY_VIRTUAL_KEY` | Portkey virtual key (provider/credential alias, e.g. `aws-bedrock-use2`). Required when `PROVIDER=portkey`. |
| `CANDIDATE_MATCH_AGENT_ANTHROPIC_API_KEY` | Direct Anthropic API key. Required only when `PROVIDER=anthropic`. |

`.env` is gitignored — never commit it.

## How to run this project

```bash
uv run candidate-match-agent-cli
```

## How to run the tests

Tests live under `tests/` and use `pytest` + `pytest-cov`. `uv sync` already installs them as dev dependencies.

```bash
uv run pytest
```

This also prints a coverage report for `src/candidate_match_agent_cli` (configured in `pyproject.toml`); a line is only "covered" if a test actually executes it, and `Missing` lists any line numbers that aren't.

`labs-agent-lib` has its own repo, `pyproject.toml`, and test suite with a 100% coverage gate — see
`../labs-agent-lib/README.md` and `../labs-agent-lib/PUBLISHING.md`.


uv run python -m candidate_match_agent_cli.coordinators "us.anthropic.claude-sonnet-5" "resume/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf"