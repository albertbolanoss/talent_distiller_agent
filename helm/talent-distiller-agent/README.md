# Talent Distiller Agent Helm Chart

Deploys the Talent Distiller Agent (resume/job-posting upload API + background processing loop)
to a Kubernetes cluster. The chart installs a `Deployment`, a `Service`, a `ConfigMap`, and a
`Secret`.

All commands below assume the repository root as the working directory.

## Prerequisites

1. [Docker](https://docs.docker.com/get-docker/), to build the image.
2. A Kubernetes cluster reachable via `kubectl`. Pick one:
   *   **Production / shared environments:** any managed or self-hosted Kubernetes cluster.
   *   **Local development:** [minikube](https://minikube.sigs.k8s.io/docs/start/), or
       [Rancher Desktop](https://rancherdesktop.io/) with its bundled Kubernetes enabled.
3. [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl)
4. [Helm](https://helm.sh/docs/intro/install/)

## 1. Build the Docker image

```sh
# Build and run locally
docker build -t talent-distiller-agent:local .
docker run --rm -p 8080:8080 --env-file .env talent-distiller-agent:local

# Build and publish to a registry
docker build -t talent-distiller-agent:0.1.4 .
docker tag talent-distiller-agent:0.1.4 luigisamurai/talent-distiller-agent:0.1.4
docker push luigisamurai/talent-distiller-agent:0.1.4
```

The image's entrypoint is `talent-distiller-agent-api` (HTTP API + background loop).

To use a published image instead of building locally, point `image.repository`/`image.tag` in
`values.yaml` (or via `--set`) at it; `imagePullPolicy` defaults to `IfNotPresent`.

## 2. Install Redis

This chart doesn't deploy Redis itself (see the `config.redisHost` comment in `values.yaml`) —
install it separately first, with the [bitnami/redis](https://artifacthub.io/packages/helm/bitnami/redis)
chart:

```sh
# Add the bitnami repository and update
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install redis instance from the helm chart bitnami/redis
helm install redis bitnami/redis

# Get credential from secret
kubectl get secret --namespace default redis -o jsonpath="{.data.redis-password}" | base64 --decode

# Create the port forward to allow the communication
kubectl port-forward pod/redis-master-0 6379:6379
```

The chart creates a `redis-master` Service — point the application at it with
`config.redisHost=redis-master` (same namespace, see step 3) and pass the password printed above
as `secrets.redisPassword`.

### Install RedisInsight (optional GUI)

[RedisInsight](https://redis.io/insight/) is Redis's GUI for browsing keys and running commands
against the instance above. Redis doesn't publish an official chart for it, but
[mrnim94/redisinsight](https://github.com/mrnim94/redisinsight) packages the official
`redis/redisinsight` image:

```sh
# Add the repository and update
helm repo add redisinsight https://mrnim94.github.io/redisinsight/
helm repo update

# Install RedisInsight - storageClassName must be set explicitly: the chart defaults it to ""
# (meaning "no dynamic provisioning"), which leaves its PVC permanently Pending even when a
# default StorageClass exists. Check yours with `kubectl get storageclass`.
helm install redisinsight redisinsight/redisinsight --set persistence.storageClassName=standard

# Create the port forward to allow the communication (its Service is ClusterIP on port 5540)
kubectl port-forward svc/redisinsight 5540:5540
```

Open http://localhost:5540, then add a database connection using host `redis-master`, port
`6379`, and the password retrieved above.


**Connection URL**: redis://default:password@redis-master:6379

## 3. Deploy to Kubernetes

If you're deploying to a production/shared cluster, make sure `kubectl config current-context`
already points at it, then skip to the `helm install` step below. For local development, start
(or switch to) one of the following instead — only run one at a time, since minikube and Rancher
Desktop's Kubernetes conflict over ports and the active `kubectl` context:

**Option A — minikube:**
```sh
minikube start
```

**Option B — Rancher Desktop:** enable Kubernetes in its preferences
(*Kubernetes Settings → Enable Kubernetes*), then point `kubectl` at it:
```sh
kubectl config use-context rancher-desktop
```

Then install the chart, pointing it at the Redis instance from step 2:

```sh
# Install the chart
helm install talent-distiller-agent ./helm/talent-distiller-agent --set secrets.portkeyApiKey="" --set config.resumePollIntervalSeconds="30" --set config.redisHost="redis-master" --set secrets.redisPassword="" --set replicaCount="1" --set image.tag="0.1.4"

# ...or upgrade an existing install, overriding a value
helm upgrade talent-distiller-agent ./helm/talent-distiller-agent --set secrets.portkeyApiKey="" --set config.resumePollIntervalSeconds="30" --set config.redisHost="redis-master" --set secrets.redisPassword="<password from step 2>" --set replicaCount="1"  --set image.tag="0.1.3"

# Check the pods came up
kubectl get pods -l app.kubernetes.io/instance=talent-distiller-agent
```

## 4. Access the service

The `Service` is `NodePort` by default (switch `service.type` to `ClusterIP` + an Ingress, or
`LoadBalancer`, for a real cluster — see the `Configuration` table below), so any of these work:

**port-forward to localhost (any cluster):**
```sh
kubectl port-forward svc/talent-distiller-agent 8084:80
# then open http://localhost:8080
```

**Note : !important; Make sure you have deployed and enabled the MCP servers for the data extraction tools and set up port forwarding for local testing.

[Guide to deploy tool MCP servers](https://github.com/albertbolanoss/mcp_skills_extractor_agents/blob/main/helm/mcp-skills-extractor-agents/README.md).

```sh
# forwarding more than one Service at once needs a distinct local port each, in separate
# terminals, e.g.:

kubectl port-forward svc/skill-agent-technical 8000:80
# then point an MCP client at http://localhost:8000/mcp

kubectl port-forward svc/skill-agent-soft 8001:80
# then point an MCP client at http://localhost:8001/mcp

kubectl port-forward svc/skill-agent-certifications 8002:80
# then point an MCP client at http://localhost:8002/mcp

kubectl port-forward svc/skill-agent-languages 8003:80
# then point an MCP client at http://localhost:8003/mcp

```

## 5. Execute the upload endpoints

```sh
curl -F "file=@document_samples/resume_sample.txt" http://localhost:8084/resume

curl -F "file=@document_samples/job_posting_sample.txt" http://localhost:8084/job_posting
```

## 6. Install mcp_skills_extractor_agents 

Follow the instructions provided in the [README Helm Chart file](https://github.com/albertbolanoss/mcp_skills_extractor_agents/helm/mcp-skills-extractor-agents/README.md).


## Configuration

| Key | Description |
|---|---|
| `replicaCount` | Number of pod replicas (default: `1`). |
| `image.repository` / `image.tag` | Image to deploy. |
| `service.type` | `NodePort` by default for easy `minikube service` access; switch to `ClusterIP` (with an Ingress) or `LoadBalancer` for a real cluster. |
| `config.*` | Non-secret settings (provider, log level, resume/job-posting dir/polling, coordinator model, Redis host/db, Portkey virtual key alias, etc.) — rendered into the `ConfigMap`. |
| `secrets.portkeyApiKey` / `secrets.anthropicApiKey` / `secrets.redisPassword` | Credentials — rendered into the `Secret`. |

The chart ships with **empty placeholder credentials** (see `secrets.*` in `values.yaml`) — never
commit real values there. Pass them at install/upgrade time instead:

```sh
helm install talent-distiller-agent ./helm/talent-distiller-agent \
  --set secrets.portkeyApiKey=***
```

or with a separate, untracked values file (`helm install ... -f secrets.values.yaml`).

`GET /healthz`, `POST /resume`, and `POST /job_posting` work without credentials; the background
loop needs real Portkey/Anthropic credentials to actually process an uploaded document.

## Notes

- Each pod's `resume/` and `job_posting/` directories are ephemeral, pod-local `emptyDir`s — a
  document uploaded to one pod is only processed by that same pod's background loop, not shared
  across other replicas.
- This chart is deliberately scoped to a single service for now; the plan is for several of these
  agents to eventually talk to each other over MCP, which isn't implemented yet.
