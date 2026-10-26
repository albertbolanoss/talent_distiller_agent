# candidate-match-agent

This AI agent analyzes job postings against resumes to identify matching skills and rank candidates.

## Prerequisites.

- [Python 3.14](https://www.python.org/downloads/) or [UV](https://docs.astral.sh/uv/getting-started/installation/)

## How to execute this project

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
         uv run candidate-match-agent
         ```

   ### Option 2: pip (no uv required)

      `pip` works too — it automatically fetches the build backend (`uv-build`). Note: this skips `uv.lock`, so dependency versions may differ slightly from uv's.

         ```bash
         python -m venv .venv
         .venv\Scripts\activate      # Windows
         source .venv/bin/activate   # macOS/Linux

         pip install -e .
         candidate-match-agent
         ```
