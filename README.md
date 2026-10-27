# candidate-match-agent

This AI agent analyzes job postings against resumes to identify matching skills and rank candidates.

## Prerequisites.

- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## How to install dependencies

1. Clone the repo (or download and unzip it):

   ```bash
   git clone https://github.com/albertbolanoss/candidate-match-agent.git
   cd candidate-match-agent
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
uv run candidate-match-agent
```

## How to run the tests

Tests live under `tests/` and use `pytest` + `pytest-cov`. `uv sync` already installs them as dev dependencies.

```bash
uv run pytest
```

This also prints a coverage report for `libs/file_reader` (configured in `pyproject.toml`); a line is only "covered" if a test actually executes it, and `Missing` lists any line numbers that aren't.


uv run python -m candidate_match_agent.coordinators "us.anthropic.claude-sonnet-5" "resume/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf"