# System Design — Architecture Diagrams

Diagrams for the two repositories that make up this hub-and-spoke multi-agent system:

- **talent_distiller_agent** (this repo) — upload API + coordinator orchestration.
- **mcp-skills-extractor-agents** (sibling repo, `../../mcp-skills-extractor-agents/src`) — the MCP server exposing the 4 extraction sub-agents.

## How to view

**Zero install (recommended):** double-click `index.html`, or open it with `File > Open`
in any browser. It renders all three diagrams client-side via Mermaid.js (loaded from a
CDN) — no local Node/npm, no browser extension, no account.

**Alternative viewers**, using the standalone `.mmd` sources below:

- Paste a file's contents into the [Mermaid Live Editor](https://mermaid.live) (mermaid.ai).
- Open it in VS Code with the "Markdown Preview Mermaid Support" or "Mermaid" extension.
- Paste it into a GitHub/GitLab Markdown file inside a ` ```mermaid ` code block — both render Mermaid natively.

## Contents

| File | Diagram | What it shows |
| --- | --- | --- |
| `talent_distiller_agent_architecture.mmd` | Component/flowchart | The orchestration service: in-pod API + poller, the Coordinator agent, the 3-point guardrail, Redis checkpointing, and the network boundary to the extraction MCP service. |
| `mcp_skills_extractor_agents_architecture.mmd` | Component/flowchart | The extraction microservice: transport layer, the 4 independent sub-agents, their canonical-taxonomy grounding, and the shared validate/self-correct/fail pattern every tool call runs. |
| `end_to_end_sequence.mmd` | Sequence diagram | One full file-processing cycle across both services — upload, polling, parallel tool fan-out, bounded self-correction, checkpointing, and the outer retry-by-missing-field loop. |
| `index.html` | Viewer | Self-contained page that renders all three diagrams above with a legend and short "skills demonstrated" callouts per diagram. |

## What these diagrams are meant to demonstrate

- **AI agent orchestration** — a hub-and-spoke coordinator that fans a document out to
  parallel, specialized sub-agents in a single turn, rather than one monolithic prompt.
- **Microservice boundaries via a protocol, not a library** — the extraction capability is
  a separate MCP server reachable only over the network (stdio/HTTP/SSE), independently
  deployable, versioned, and scaled from the orchestration service.
- **Resilience at two levels** — a bounded self-correction loop inside each sub-agent call
  (schema validation → retry → fail), and an outer, Redis-backed revision/retry loop in the
  coordinator that only re-does the fields still missing, so partial progress survives
  crashes, restarts, and pod rescheduling.
- **Observability** — structured, leveled logging at every phase in both services, plus
  Kubernetes liveness/readiness probes wired into the Helm charts.

All diagram sources were syntax-checked against the real Mermaid parser (`mermaid.parse()`)
before being committed here.

## Related

- [`../prompt_log_and_agent_transcript.md`](../prompt_log_and_agent_transcript.md) -
  the Prompt Log / Agent Transcript observability feature that extends the
  `end_to_end_sequence.mmd` flow above with a durable, correlated record of every
  prompt/response/tool-call in both services.
