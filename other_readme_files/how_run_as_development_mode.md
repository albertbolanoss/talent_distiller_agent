# Run using Development Mode

Development mode is designed to run on your local machine, using containers to host certain services required by this application.

## Prerequisites

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager (recommended) or [Python 3.14 or higher](https://www.python.org/downloads/).
2. Install a Container Management tool (recommended: [Rancher Desktop](https://rancherdesktop.io/) or Docker Engine).
3. A running Redis server (local or containerized).
4. A Redis Graphical User Interface (GUI) (recommended: RedisInsight).

## Service Setup

### 1. Install Project Dependencies

**Option A: Using uv**

```sh
# Sync dependencies and create the virtual environment automatically
uv sync
```

**Option B: Using Python 3.14 and `requirements.txt`**

```sh
# Create and activate a virtual environment in the project root folder
python -m venv .venv
.venv\Scripts\activate

# Install the project dependencies
pip install -r requirements.txt

# Install the project itself
pip install .
```

### 2. Install Rancher Desktop or Docker Engine

Download and install Docker according to your operating system.

### 3. Install Redis Server

```sh
# Create a network for the services
docker network create talent_distiller_agent

# Create the Redis server container
docker run -d --name redis --network talent_distiller_agent -p 6379:6379 redis:latest redis-server --requirepass "password"
```

### 4. Install Redis GUI

```sh
# Create the RedisInsight container (GUI)
docker run -d --name redisinsight --network talent_distiller_agent -p 5540:5540 redis/redisinsight:latest

## Open your browser, enter the URL, and then create the database connection using the Connection URL
http://localhost:5540/
Connection URL: redis://default:password@redis:6379
```

## Configuring the .env file

Copy the example file and fill in your values:

```sh
cp .env.example .env
```

| Variable | Description |
|---|---|
| `LABS_AGENT_LIB_PROVIDER` | Gateway to route through: `portkey` (default) or `anthropic`. |
| `LABS_AGENT_LIB_LOG_LEVEL` | Log verbosity: `DEBUG`, `INFO` (default), `WARNING`, or `ERROR`. |
| `LABS_AGENT_LIB_PORTKEY_API_KEY` | Portkey workspace key. Required when `PROVIDER=portkey`. Ask your AI Academy facilitator for one. |
| `LABS_AGENT_LIB_PORTKEY_VIRTUAL` | Provider/credential alias configured in the Portkey dashboard (e.g. `aws-bedrock-use2`). Not a secret, just an identifier. |
| `LABS_AGENT_LIB_ANTHROPIC_API_KEY` | Direct Anthropic API key. Required only when `PROVIDER=anthropic`. |
| `LABS_AGENT_LIB_DISABLE_PROMPT_CACHING` | Disables Anthropic prompt caching (`cache_control`) for the agent's requests. Defaults to `false`. |
| `TALENT_DISTILLER_AGENT_RESUME_DIR` | Directory polled for resume files. Defaults to `resume`. |
| `TALENT_DISTILLER_AGENT_RESUME_POLL_INTERVAL_SECONDS` | How often (in seconds) `resume_dir` is polled for new files. Defaults to `10`. |
| `TALENT_DISTILLER_AGENT_RESUME_MAX_FILES_PER_BATCH` | Max resume files processed per polling batch. Defaults to `3`. |
| `TALENT_DISTILLER_AGENT_COORDINATOR_PROCESSED_FOLDER` | Folder processed resumes are moved to. Defaults to `<RESUME_DIR>/processed`. |
| `TALENT_DISTILLER_AGENT_COORDINATOR_FAILED_FOLDER` | Folder resumes are moved to once `COORDINATOR_MAX_REVISION_NUMBER` is exceeded. Defaults to `<RESUME_DIR>/failed`. |
| `TALENT_DISTILLER_AGENT_JOB_POSTING_DIR` | Directory polled for job posting files. Defaults to `job_posting`. |
| `TALENT_DISTILLER_AGENT_JOB_POSTING_POLL_INTERVAL_SECONDS` | How often (in seconds) `job_posting_dir` is polled for new files. Defaults to `10`. |
| `TALENT_DISTILLER_AGENT_JOB_POSTING_MAX_FILES_PER_BATCH` | Max job posting files processed per polling batch. Defaults to `3`. |
| `TALENT_DISTILLER_AGENT_JOB_POSTING_PROCESSED_FOLDER` | Folder processed job postings are moved to. Defaults to `<JOB_POSTING_DIR>/processed`. |
| `TALENT_DISTILLER_AGENT_JOB_POSTING_FAILED_FOLDER` | Folder job postings are moved to once `COORDINATOR_MAX_REVISION_NUMBER` is exceeded. Defaults to `<JOB_POSTING_DIR>/failed`. |
| `TALENT_DISTILLER_AGENT_SKILL_AGENT_TECHNICAL_MCP_URL` / `_SOFT_MCP_URL` / `_CERTIFICATIONS_MCP_URL` / `_LANGUAGES_MCP_URL` | Per-tool `candidate-skill-agent` MCP server URL (streamable HTTP, must end in `/mcp`). All four default to `http://127.0.0.1:8000/mcp`; override one independently only if that tool is split off onto its own server. |
| `TALENT_DISTILLER_AGENT_COORDINATOR_MODEL` | Model used by the coordinator agent. Defaults to `us.anthropic.claude-haiku-4-5-20251001-v1:0`. |
| `TALENT_DISTILLER_AGENT_COORDINATOR_MAX_REVISION_NUMBER` | Max extraction revisions before a file is marked failed. Defaults to `3`. |
| `TALENT_DISTILLER_AGENT_REDIS_HOST` | Redis host for the resume-extraction job store. Defaults to `localhost`. |
| `TALENT_DISTILLER_AGENT_REDIS_PASSWORD` | Redis auth password, only needed if your instance requires one. Defaults to no auth. |
| `TALENT_DISTILLER_AGENT_REDIS_DB` | Redis logical database index. Defaults to `0`. |
| `PORT` | Port the resume-upload API server listens on. Defaults to `8080`. Unprefixed — not part of any Settings model. |

`.env` is gitignored — never commit it. `LABS_AGENT_LIB_PORTKEY_VIRTUAL` ships in `.env.example` with an empty default since it's optional; set it locally if your Portkey workspace routes through a specific provider/credential alias:

```sh
LABS_AGENT_LIB_PORTKEY_VIRTUAL=aws-bedrock-use2
```

## Run App and MCP Server.

**Option A: Using uv**

```sh
# Start the MCP server (from the mcp_skills_extractor_agents repo, in a separate terminal)
cd ../mcp_skills_extractor_agents
uv run python -m mcp_skills_extractor_agents.main --protocol http --host 127.0.0.1 --port 8000

# Start this application (from this repo's root, in another terminal)
cd ../talent_distiller_agent
uv run talent-distiller-agent-api
```

**Option B: Using Python 3.14 and the virtual environment**

```sh
# Start the MCP server (from the mcp_skills_extractor_agents repo, in a separate terminal)
cd ../mcp_skills_extractor_agents
.venv\Scripts\activate
python -m mcp_skills_extractor_agents.main --protocol http --host 127.0.0.1 --port 8000

# Start this application (from this repo's root, in another terminal)
cd ../talent_distiller_agent
.venv\Scripts\activate
talent-distiller-agent-api
```

## Run MCP Server & 

## 6. Install mcp_skills_extractor_agents 

Follow the instructions provided in the [README file](https://github.com/albertbolanoss/mcp_skills_extractor_agents/README.md).


## Run unit tests.

**Option A: Using uv**

```sh
uv run pytest
```


**Option B: Using Python**

```sh
pytest
```