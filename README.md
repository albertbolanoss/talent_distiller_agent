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
| `CANDIDATE_MATCH_AGENT_ANTHROPIC_API_KEY` | Direct Anthropic API key. Required only when `PROVIDER=anthropic`. |

`.env` is gitignored — never commit it. Not in `.env.example` because it's not required, but if your Portkey
workspace routes through a specific provider/credential alias, set it locally with:

```bash
CANDIDATE_MATCH_AGENT_PORTKEY_VIRTUAL=aws-bedrock-use2
```

(It's not a secret — just an identifier — so it's read as a plain setting, not through the Secret in the
Helm chart.)

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

## Docker

```bash
# Run container local
docker build -t candidate-match-agent-cli:local .
docker run --rm -p 8080:8080 --env-file .env candidate-match-agent-cli:local

# Publish image
docker build -t candidate-match-agent-cli:local .
docker tag candidate-match-agent-cli:local luigisamurai/candidate-match-agent-cli:local
docker push luigisamurai/candidate-match-agent-cli:local

```

The image runs `candidate-match-agent-api` (the HTTP API + background loop) as its entrypoint.

## Deploying to Kubernetes (minikube) with Helm

The chart lives at `helm/candidate-match-agent-cli/` and installs a Deployment (3 replicas by
default), a Service, a ConfigMap, and a Secret.

```bash
# Start minikube
minikube start

# Start RancharDesktop without kubernetes (for docker in windows)

# Install deployment
helm install candidate-match-agent-cli ./helm/candidate-match-agent-cli
helm upgrade candidate-match-agent-cli ./helm/candidate-match-agent-cli --set secrets.portkeyApiKey=""

kubectl get pods -l app.kubernetes.io/instance=candidate-match-agent-cli

# Get service URL
Opción 1 — minikube service (abre el navegador o te da la URL):
minikube service candidate-match-agent-cli --url



Opción 2 — acceso directo con el NodePort (32392):
minikube ip
y luego entra a http://<ip-de-minikube>:32392

Opción 3 — port-forward (si prefieres localhost y un puerto fijo):
kubectl port-forward svc/candidate-match-agent-cli 8080:80
y accedes en http://localhost:8080

# request
curl -F "file=@input/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf" http://172.21.252.79:32190/resumes

```

To use a real Docker Hub image instead, push with the `Dockerfile` in this repo and set
`image.repository`/`image.tag` to point at it (`imagePullPolicy` defaults to `IfNotPresent`).

The chart's Secret (`templates/secret.yaml`) ships with empty placeholder credentials — see
`secrets.*` in `helm/candidate-match-agent-cli/values.yaml`. `GET /healthz` and `POST /resumes`
work without them; the background loop needs real Portkey/Anthropic credentials (via
`--set secrets.xxx=...` or an untracked values file) to actually process a resume once uploaded.

Each pod's `resume/` directory is an ephemeral, pod-local `emptyDir` — a resume uploaded to one
pod is processed by that same pod's own background loop, not shared across the other replicas.

This chart is deliberately scoped to a single service for now; the plan is for several of these
agents to eventually talk to each other over MCP, which isn't implemented yet.