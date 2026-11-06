# About This Project

This project is a scalable, retry-resilient multi-agent AI system designed to drastically optimize reading and extraction times in IT recruitment. Built on a hub-and-spoke architecture, it processes both unstructured IT resumes and job postings to establish a unified taxonomy. The system extracts technical skills, soft skills, certifications, and languages in parallel while inferring seniority and experience, ultimately consolidating standardized profiles into a Redis database to eliminate manual review and power downstream automation.

## Core Workflow

The architecture executes through five automated phases:

*   **1. Async Intake & Triage:** Automatically ingests and classifies resumes and job postings without manual formatting, assigning tracking IDs and preparing the context for asynchronous processing.
*   **2. Parallel Skill Extraction:** A central coordinator dispatches sub-agents in parallel to concurrently extract technical skills, soft skills, languages, and certifications, while automatically inferring the candidate's seniority level and years of experience.
*   **3. Common Language Alignment:** Translates every profile and vacancy from its raw source into a unified taxonomy of competencies and proficiency levels, eliminating wording ambiguities to guarantee standardized data.
*   **4. Quality Guardrails & Observability:** Automated checks audit each extraction to catch incomplete data and execute intelligent retries before proceeding, all while emitting real-time telemetry on the execution flow.
*   **5. Consolidation & Persistence:** A consolidation agent merges the validated outputs into a structured database profile, providing immediate visibility to recruiters and enabling direct consumption by downstream automation systems.

## Tech Stack Highlights

*   **Routing & Orchestration:** Asynchronous REST API with FastAPI, initial routing via Claude Agent SDK, and a Coordinator Guardrails module.
*   **Validation:** Orchestration prompts enforced by a single reference dictionary and strict data contract validation using Pydantic.
*   **State & Persistence:** Consolidator agent state management in Redis coupled with robust database persistence.

## Project Repositories

This project consists of three GitHub repositories, each with specific responsibilities and reusable libraries:

*   **[Talent Distiller Agent](https://github.com/albertbolanoss/talent_distiller_agent)**: The main application responsible for exposing the document upload endpoint and initiating the coordinator agent workflow (Hub-and-Spoke architecture).
*   **[mcp_skills_extractor_agents](https://github.com/albertbolanoss/mcp_skills_extractor_agents)**: The MCP server that grants access to the specialized agent workflow for competency extraction (technical skills, soft skills, certifications, and languages).
*   **[labs-agent-lib](https://github.com/albertbolanoss/labs-agent-lib)**: A shared library containing common utilities and shared code for managing projects built with Claude agents.

**Clone or download the repositories listed above into a specific folder**:

```sh
# Command to clone from github the repositories:

git clone https://github.com/albertbolanoss/talent_distiller_agent.git
git clone https://github.com/albertbolanoss/mcp_skills_extractor_agents.git
git clone https://github.com/albertbolanoss/labs-agent-lib
```

## How to run it based on the selected mode

There are three ways to run it

1. [Go to how using Development Mode](#run-using-development-mode):  Install the tools on the machine and in the virtual environment to run the services using Python 3.14.
1. [Go to how using Deployment mode](./helm/talent-distiller-agent/README.md): Use Kubernetes cluster or Minikube or Rancher Desktop with kubernetes plugin to deploy and scale the application. 

## Run using Development Mode

Development mode is designed to run on your local machine, using containers to host certain services required by this application.

### Prerequisites

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager (recommended) or [Python 3.14 or higher](https://www.python.org/downloads/).
2. Install a Container Management tool (recommended: [Rancher Desktop](https://rancherdesktop.io/) or Docker Engine).
3. A running Redis server (local or containerized).
4. A Redis Graphical User Interface (GUI) (recommended: RedisInsight).

### Service Setup

#### 1. Install Project Dependencies

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

#### 2. Install Rancher Desktop or Docker Engine

Download and install Docker according to your operating system.

#### 3. Install Redis Server

```sh
# Create a network for the services
docker network create talent_distiller_agent

# Create the Redis server container
docker run -d --name redis --network talent_distiller_agent -p 6379:6379 redis:latest redis-server --requirepass "password"
```

#### 4. Install Redis GUI

```sh
# Create the RedisInsight container (GUI)
docker run -d --name redisinsight --network talent_distiller_agent -p 5540:5540 redis/redisinsight:latest

## Open your browser, enter the URL, and then create the database connection using the Connection URL
http://localhost:5540/
Connection URL: redis://default:password@redis:6379
```

#### 5. Configuring the .env file

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
| `TALENT_DISTILLER_AGENT_OBSERVABILITY_ENABLED` | Master on/off switch for the prompt log and agent transcript (see [`documentation/prompt_log_and_agent_transcript.md`](./documentation/prompt_log_and_agent_transcript.md)). Defaults to `true`. |
| `TALENT_DISTILLER_AGENT_PROMPT_LOG_DIR` | Directory where prompt-log JSONL files are written. Defaults to `documentation/prompt_log`. |
| `TALENT_DISTILLER_AGENT_AGENT_TRANSCRIPT_DIR` | Directory where agent-transcript JSONL files are written. Defaults to `documentation/agent_transcript`. |
| `PORT` | Port the resume-upload API server listens on. Defaults to `8080`. Unprefixed — not part of any Settings model. |

`.env` is gitignored — never commit it. `LABS_AGENT_LIB_PORTKEY_VIRTUAL` ships in `.env.example` with an empty default since it's optional; set it locally if your Portkey workspace routes through a specific provider/credential alias:

```sh
LABS_AGENT_LIB_PORTKEY_VIRTUAL=aws-bedrock-use2
```

#### 6. Run App and MCP Server.

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


#### 7. How to Start Uploading Documents

After running the application in a specific mode, you can start using it to upload your documents in the following formats: (pdf, docx, md, txt).

The API exposes one upload endpoint per document type. Both accept a multipart `POST` request with the file in the `file` field, and store it in the directory the background process polls for extraction. You can try them with the sample files under [`document_samples/`](./document_samples):

*   **Resumes** — `POST /resume`, saved into `resume_dir`:

    ```sh
    curl -X POST http://localhost:8080/resume \
      -F "file=@document_samples/resume_sample.txt"
    ```

*   **Job postings** — `POST /job_posting`, saved into `job_posting_dir`:

    ```sh
    curl -X POST http://localhost:8080/job_posting \
      -F "file=@document_samples/job_posting_sample.txt"
    ```


## Run unit tests.

**Option A: Using uv**

```sh
uv run pytest
```


**Option B: Using Python**

```sh
pytest
```

