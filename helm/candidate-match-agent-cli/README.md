# candidate-match-agent-cli Helm Chart

Deploys the resume-matching agent (resume-upload API + background resume-processing loop) to
Kubernetes. The chart installs a `Deployment`, a `Service`, a `ConfigMap`, and a `Secret`.

All commands below assume the repository root as the working directory.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [minikube](https://minikube.sigs.k8s.io/docs/start/) (or any Kubernetes cluster)
- [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl)
- [Helm](https://helm.sh/docs/intro/install/)

## 1. Build the Docker image

```bash
# Build and run locally
docker build -t candidate-match-agent-cli:local .
docker run --rm -p 8080:8080 --env-file .env candidate-match-agent-cli:local

# Build and publish to a registry
docker build -t candidate-match-agent-cli:0.1.0 .
docker tag candidate-match-agent-cli:0.1.0 luigisamurai/candidate-match-agent-cli:0.1.0
docker push luigisamurai/candidate-match-agent-cli:0.1.0
```

The image's entrypoint is `candidate-match-agent-api` (HTTP API + background loop).

To use a published image instead of building locally, point `image.repository`/`image.tag` in
`values.yaml` (or via `--set`) at it; `imagePullPolicy` defaults to `IfNotPresent`.

## 2. Deploy to Kubernetes

```bash
# Start the cluster
minikube start

# > **Windows + Docker Desktop:** if you're running Rancher Desktop or Docker Desktop alongside
# > minikube, disable its bundled Kubernetes so the two don't conflict.

# Install the chart
helm install candidate-match-agent-cli ./helm/candidate-match-agent-cli --set secrets.portkeyApiKey="" --set config.resumePollIntervalSeconds="30"

# ...or upgrade an existing install, overriding a value
helm upgrade candidate-match-agent-cli ./helm/candidate-match-agent-cli --set secrets.portkeyApiKey="" --set config.resumePollIntervalSeconds="30"

# Check the pods came up
kubectl get pods -l app.kubernetes.io/instance=candidate-match-agent-cli
```
kubec
## 3. Access the service

The `Service` is `NodePort` by default, so any of these work:

**Option 1 — `minikube service` (opens a browser or prints the URL):**
```bash
minikube service candidate-match-agent-cli --url
```

**Option 2 — direct NodePort access:**
```bash
minikube ip
# then open http://<minikube-ip>:<node-port>  (see `kubectl get svc` for the port)
```

**Option 3 — port-forward to localhost:**
```bash
kubectl port-forward svc/candidate-match-agent-cli 8080:80
# then open http://localhost:8080


## 4. Execute upload resume endpoint

curl -F "file=@input/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf" [Service URL]/resumes

```

## Configuration

| Key | Description |
|---|---|
| `replicaCount` | Number of pod replicas (default: `1`). |
| `image.repository` / `image.tag` | Image to deploy. |
| `service.type` | `NodePort` by default for easy `minikube service` access; switch to `ClusterIP` (with an Ingress) or `LoadBalancer` for a real cluster. |
| `config.*` | Non-secret settings (provider, log level, resume dir/polling, Portkey virtual key alias, etc.) — rendered into the `ConfigMap`. |
| `secrets.portkeyApiKey` / `secrets.anthropicApiKey` | Credentials — rendered into the `Secret`. |

The chart ships with **empty placeholder credentials** (see `secrets.*` in `values.yaml`) — never
commit real values there. Pass them at install/upgrade time instead:

```bash
helm install candidate-match-agent-cli ./helm/candidate-match-agent-cli \
  --set secrets.portkeyApiKey=***
```

or with a separate, untracked values file (`helm install ... -f secrets.values.yaml`).

`GET /healthz` and `POST /resumes` work without credentials; the background loop needs real
Portkey/Anthropic credentials to actually process an uploaded resume.

## Notes

- Each pod's `resume/` directory is an ephemeral, pod-local `emptyDir` — a resume uploaded to one
  pod is only processed by that same pod's background loop, not shared across other replicas.
- This chart is deliberately scoped to a single service for now; the plan is for several of these
  agents to eventually talk to each other over MCP, which isn't implemented yet.
