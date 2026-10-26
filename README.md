# candidate-match-agent

This AI agent analyzes job postings against resumes to identify matching skills and rank candidates.

## Prerequisites.

- [Python 3.14](https://www.python.org/downloads/) or [UV](https://docs.astral.sh/uv/getting-started/installation/)

## How to install dependencies

1. Clone the repo (or download and unzip it):

   ```bash
   git clone https://github.com/albertbolanoss/candidate-match-agent.git
   cd candidate-match-agent
   ```

2. Install dependencies with one of these options:

   ### Option 1: uv (recommended)

      Installs the exact dependency versions pinned in `uv.lock`.

         ```bash
         uv sync
         ```

   ### Option 2: pip (no uv required)

      `pip` works too — it automatically fetches the build backend (`uv-build`). Note: this skips `uv.lock`, so dependency versions may differ slightly from uv's.

         ```bash
         python -m venv .venv
         .venv\Scripts\activate      # Windows
         source .venv/bin/activate   # macOS/Linux

         pip install -e .
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

`.env` is gitignored — never commit it.

## How to run this project

### With uv

```bash
uv run candidate-match-agent
```

### With python

Activate the virtual environment first if it isn't active yet, then run:

```bash
candidate-match-agent
```
