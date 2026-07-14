# NeuraSWE — Autonomous AI Software Engineering Agent

> NeuraSWE turns GitHub issues and Jira tickets into autonomous coding runs. It maps an issue to a repository, clones/indexes the codebase, runs a ReAct-style coding agent in a sandbox, streams every reasoning/tool step to a dashboard, verifies changes with tests, and can open a GitHub pull request.

This project is a from-scratch agentic software engineering platform built with **FastAPI, React, PostgreSQL, Redis, ChromaDB, Docker, Socket.IO, GitHub API, Jira Automation, and multi-provider LLM fallback**. It does not use LangChain, CrewAI, or another agent framework; the prompt loop, tool registry, trajectory handling, queue processor, and realtime trace system are implemented directly.

---

## Demo videos

**1. GitHub issue → NeuraSWE run → direct resolution**

https://github.com/user-attachments/assets/f68e549c-903a-47c0-a2d5-ec5ff8d96bed

**2. Jira ticket status → NeuraSWE trigger → resolution flow**

https://github.com/user-attachments/assets/aaedae4d-565f-43a6-8dfe-076cb1672d21


**3. Screenshots of PR and solved issue from the dashboard**

Dashboard solved issue:
<img width="3430" height="1818" alt="image" src="https://github.com/user-attachments/assets/908fbd81-bc33-48f5-abda-a7671d867691" />


Pull request created by NeuraSWE:

<img width="3430" height="1818" alt="image" src="https://github.com/user-attachments/assets/25560bb7-7ae0-4c86-bafa-e7f186a36e7b" />

## What NeuraSWE does

- **GitHub issue execution**: fetches a GitHub issue, builds an internal run, and lets the agent fix the target repo.
- **Jira-triggered execution**: Jira Automation can call `/api/webhook/jira` when a ticket enters `NeuraSWE`, `In Progress`, or another configured status.
- **Repository mapping**: Jira project keys map to GitHub repositories, for example `SCRUM=Gaurav598/NeuraSWE`.
- **Autonomous coding loop**: the agent searches code, reads files, edits files, runs tests, inspects diffs, and submits a solution.
- **Real-time dashboard**: React UI shows run state, agent activity, tool calls, observations, diffs, touched files, tests, errors, and PR links.
- **Run controls**: active runs can be stopped; completed/failed runs can be deleted; failed runs can be bulk-cleaned for demos.
- **Multi-provider resilience**: supports Gemini, Groq, OpenRouter, OpenAI-compatible APIs, and local Ollama fallback.
- **Sandboxed execution**: tools run inside an isolated Docker sandbox with memory/CPU limits.

## What's inside

| Layer | Technology |
|------|------------|
| API + webhooks | FastAPI + Uvicorn |
| Real-time | python-socketio with Redis-backed cross-process events |
| Database | PostgreSQL + SQLAlchemy async + Alembic |
| Queue | arq + Redis, configurable worker concurrency |
| Vector store | ChromaDB |
| Agent LLM | OpenAI-compatible clients with provider fallback: Gemini, Groq, OpenRouter, Ollama |
| Embeddings | Ollama `nomic-embed-text` |
| Sandbox | Docker sandbox manager with local fallback |
| GitHub | PAT or GitHub App support for issue fetch, branch push, PR creation |
| Jira | Jira Automation webhook receiver with project-to-repo mapping |
| Dashboard | React 18 + Vite + Tailwind + Recharts + Framer Motion + Socket.IO |

---

## Architecture

```
GitHub issue/manual run ─┐
Jira Automation webhook ───┼──▶ FastAPI ──▶ PostgreSQL Run ──▶ arq/Redis queue ──▶ Agent Runtime
Repository dashboard ──────┘                                                        │
                                                                                    ▼
                                                                    REASON → ACT → OBSERVE loop
                                                                      tools: search_code, grep,
                                                                      read_file, edit_file,
                                                                      run_tests, git_diff,
                                                                      submit_solution
                                                                                    │
                                                                                    ▼
                                                              Docker sandbox + test verification
                                                                                    │
                                                                                    ▼
                                                              GitHub branch/PR + live dashboard
```

The ReAct loop lives in [`server/app/agent/runtime.py`](server/app/agent/runtime.py).

---

## Quick start

### Prerequisites
- Docker & Docker Compose
- 16GB+ RAM if running local Ollama embeddings/chat
- A GitHub PAT (quick start) or GitHub App (production)
- `LLM_API_KEY` for production-grade autonomous fixing

### Run the full stack

```bash
cp .env.example .env          # add GITHUB_PAT and LLM_API_KEY
docker compose up -d postgres redis chromadb ollama

# Pull models (one-time, several GB)
bash scripts/setup-ollama.sh

# Build the agent sandbox image
bash scripts/build-sandbox.sh

# Start backend, worker, and dashboard
docker compose up -d server worker client
```

- Dashboard: http://localhost:5173
- API: http://localhost:3001 — health at `/api/health`

### Run locally (without Docker for the app code)

```bash
# Backend
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # or it auto-creates tables in dev
export SANDBOX_USE_LOCAL=true # run agent commands on host instead of Docker
uvicorn app.main:app --port 3001 --reload

# Worker (separate terminal)
arq app.queue.worker.WorkerSettings

# Dashboard (separate terminal)
cd client && npm install && npm run dev
```

### Try it
1. Open the dashboard → **Repositories** → connect `owner/repo` so the codebase can be indexed.
2. Start from GitHub/manual flow: open **Issues**, pick an issue, and trigger a run.
3. Start from Jira flow: move a configured Jira ticket into the `NeuraSWE` status so Jira Automation calls `/api/webhook/jira`.
4. Open **Runs** and watch the reasoning trace, agent activity, touched files, tests, diff, errors, and PR status stream in real time.

Seed a demo run for screenshots:
```bash
cd server && python ../scripts/seed_demo.py
```

### Lightweight dashboard demo

Use this path when you only want to inspect the UI and existing run history without
pulling Ollama models or running a real agent job:

```bash
docker compose up -d postgres redis chromadb

docker build -t neuraswe-server-demo ./server
docker run --rm -d --name neuraswe-server-demo \
  --network neuraswe_default \
  -p 3001:3001 \
  -e DATABASE_URL=postgresql+asyncpg://neuraswe:neuraswe@postgres:5432/neuraswe \
  -e REDIS_URL=redis://redis:6379 \
  -e CHROMA_URL=http://chromadb:8000 \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e NODE_ENV=development \
  -e CORS_ORIGINS=http://localhost:5173 \
  neuraswe-server-demo

docker cp scripts/seed_demo.py neuraswe-server-demo:/tmp/seed_demo.py
docker exec -e PYTHONPATH=/app neuraswe-server-demo python /tmp/seed_demo.py

cd client
NPM_CONFIG_USERCONFIG=/tmp/neuraswe-empty-npmrc npm install
VITE_API_URL=http://localhost:3001 VITE_SOCKET_URL=http://localhost:3001 \
  npm run dev -- --host 0.0.0.0
```

Then open http://localhost:5173.

The demo health endpoint may show `ollama=false` if Ollama is not running. That is
expected for the dashboard-only path.

### Jira Automation setup

NeuraSWE supports Jira through a project-to-repository map. Configure `.env` like:

```bash
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_WEBHOOK_SECRET=choose-a-secret
JIRA_AUTO_STATUS=NeuraSWE,In Progress,To Do
JIRA_PROJECT_REPO_MAP=SCRUM=Gaurav598/NeuraSWE
```

For local demos, expose the backend with ngrok:

```bash
./tools/ngrok/ngrok http 3001 --config ./tools/ngrok/ngrok.yml
```

Use the generated URL in Jira Automation:

```text
https://<ngrok-host>/api/webhook/jira?secret=<JIRA_WEBHOOK_SECRET>
```

In the Jira rule, use:

- Trigger: **Work item transitioned**
- From status: blank
- To status: blank, or the specific `NeuraSWE` status
- Action: **Send web request**
- Method: `POST`
- Header: `Content-Type: text/plain`
- Body:

```text
ISSUE_KEY={{issue.key}}
PROJECT_KEY={{issue.project.key}}
STATUS={{issue.status.name}}
SUMMARY={{issue.summary}}
DESCRIPTION:
{{issue.description}}
```

`text/plain` is intentional. Jira descriptions often contain raw newlines; sending
them as unescaped JSON can produce HTTP `422` errors before NeuraSWE can process
the request.

A good Jira ticket description should include the problem, expected behavior,
actual behavior, likely file/API area, acceptance criteria, and validation command.

### Full end-to-end agent test requirements

Before testing the real GitHub issue → fix branch → PR flow, complete these:

```bash
bash scripts/setup-ollama.sh
bash scripts/build-sandbox.sh
docker compose up -d postgres redis chromadb ollama server worker client
```

You also need either `GITHUB_PAT` or GitHub App credentials in `.env`. Without
GitHub credentials, NeuraSWE can show the dashboard and demo runs but cannot clone
private repositories, push branches, or open pull requests.

For production webhook use, set `GITHUB_WEBHOOK_SECRET`. In production mode,
unsigned GitHub webhooks are rejected.

Recommended multi-provider LLM settings:

```bash
LLM_PROVIDER=openai-compatible
LLM_MODEL=gemini-2.0-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=<primary-key>
GEMINI_API_KEY=<gemini-key>
GROQ_API_KEY=<groq-key>
OPENROUTER_API_KEY=<openrouter-key>
LLM_FALLBACK_ENABLED=true
LLM_FALLBACK_ORDER=groq,primary,openrouter,ollama
LLM_TIMEOUT_S=45
OLLAMA_TIMEOUT_S=60
WORKER_MAX_JOBS=2
```

The fallback chain lets a run continue when one free-tier provider is throttled.
Ollama remains useful as the final local fallback, but hosted models are usually
more reliable for autonomous code edits and PR creation.

### Current production-readiness status

The GitHub E2E path is designed to:

1. Fetch the real GitHub issue title/body.
2. Index the target deployment branch codebase.
3. Run the agent in a sandbox using the configured `LLM_PROVIDER`.
4. Require tests before `submit_solution`.
5. Apply the generated diff to a fresh clone.
6. Create a unique `neuraswe/issue-<n>-<run>` branch.
7. Open a GitHub PR.
8. Mark the run failed if PR creation fails.

Merging is intentionally left to GitHub review/permissions.

Jira ingestion is implemented through Jira Automation. When a ticket transitions
into a configured status, Jira sends a webhook to `/api/webhook/jira`; NeuraSWE
maps the Jira project key to a GitHub repository, creates or requeues a run, and
uses the Jira summary/description as the task prompt. ClickUp ingestion is not
implemented yet, but it can use the same internal `Run` creation path.

---

## How it works

### 1. RAG code search
On connect, the repo is cloned, walked (skipping `node_modules`, lockfiles, binaries), and chunked **function-level** (Python via `ast`; other languages via declaration heuristics with a 100-line/20-overlap sliding-window fallback). Each chunk is embedded with `nomic-embed-text` and stored in ChromaDB (cosine). The agent's `search_code` tool embeds the query and returns the top-10 nearest chunks. See `server/app/indexer/`.

### 2. The ReAct loop
Each turn the LLM is given the system prompt, the issue, and the trajectory so far, and must emit a structured action. In production, OpenAI-compatible JSON mode returns `{"thought": "...", "action": {"tool": "...", "args": {...}}}` so invalid tool output is greatly reduced. The runtime still validates every action, fails fast on repeated protocol failures, and never merges code automatically.

### 3. Context management
First N steps are kept verbatim. When the trajectory exceeds the token budget, the middle steps are summarized by the LLM into one dense paragraph while the first 3 and last 7 steps are preserved (`server/app/agent/context_manager.py`).

### 4. Sandboxed tools
Tools run inside a per-issue Docker container with memory/CPU limits. `edit_file` requires the target text to appear **exactly once**; `run_command` blocks destructive patterns; `run_tests` auto-detects the runner (npm / pytest / maven / go). A `LocalSandbox` fallback exists for environments without a Docker daemon (`SANDBOX_USE_LOCAL=true`).

### 5. Self-verification + PR
`submit_solution` re-runs the suite and refuses to submit on failure. The captured diff is applied to a fresh clone, committed to `neuraswe/issue-<n>`, pushed, and a PR is opened with an auto-generated description (root cause, files changed, key decisions, baseline vs. final tests).

---

## Project layout

```
neuraswe/
├── server/            # Python backend (FastAPI)
│   ├── app/
│   │   ├── agent/     # ReAct loop, LLM client, parser, context mgmt, prompts
│   │   ├── indexer/   # clone, walk, chunk, embed, ChromaDB store (RAG)
│   │   ├── tools/     # 10 agent tools + registry
│   │   ├── sandbox/   # Docker + local sandbox managers
│   │   ├── github/    # client, webhook, PR creator + description
│   │   ├── queue/     # arq config, processor (end-to-end), worker
│   │   ├── db/        # SQLAlchemy models, schemas, CRUD
│   │   ├── api/       # runs, repositories, health, webhook routers
│   │   ├── realtime/  # Socket.IO server + emitter
│   │   └── main.py    # FastAPI + Socket.IO bootstrap
│   ├── alembic/       # migrations
│   └── tests/         # pytest suite
├── client/            # React + Vite dashboard
├── scripts/           # ollama pull, sandbox build, demo seed
└── docker-compose.yml
```

---

## REST API

```
POST   /api/webhook/github           GitHub webhook receiver
POST   /api/webhook/jira             Jira Automation webhook receiver
GET    /api/runs                     List runs (paginated, filterable)
GET    /api/runs/{id}                Run detail with all steps
GET    /api/runs/stats               Aggregate stats
POST   /api/runs/manual              Manually trigger a run {repo_id, issue_number}
POST   /api/runs/{id}/stop           Stop one queued/running run
POST   /api/runs/stop-active         Stop all queued/running runs
DELETE /api/runs/{id}                Delete a completed/stopped run
DELETE /api/runs/failed              Delete failed/timeout runs
GET    /api/repositories             List repos
POST   /api/repositories             Connect a repo {owner, name}
POST   /api/repositories/{id}/reindex
PATCH  /api/repositories/{id}/config
GET    /api/health                   DB / Redis / agent LLM / Ollama / ChromaDB
```

Socket.IO: connect, `subscribe {run_id}`, receive `agent:step` and `run:complete`.

---

## Tests

```bash
cd server
SANDBOX_USE_LOCAL=true pytest -q
```

Covers the response parser (format robustness), the chunker (AST + fallback),
`edit_file` (exact / multi-match guards), the test-summary parser, and the
context manager's truncation + compaction. It also covers production safeguards
for manual GitHub issue fetching, webhook signature enforcement, Chroma/Ollama
indexing stability, PR patch application, and PR failure status handling.

---

## Notes
- Temporary ngrok URLs change when ngrok restarts. For reliable Jira demos, use a stable public backend URL, a reserved ngrok domain, or Cloudflare Tunnel.
- Jira descriptions are accepted as newline-safe `text/plain` webhook bodies to avoid JSON escaping failures from Jira Automation smart values.
- Production reliability requires hosted LLM capacity. Free-tier Gemini/Groq/OpenRouter keys work for demos, but throttling can slow or fail long tasks.
- Built without LangChain/CrewAI: prompt construction, trajectory management, cancellation, queueing, and tool dispatch are explicit and inspectable.
- Embeddings use `nomic-embed-text`; local chat fallback can use `deepseek-coder-v2:16b`, `qwen2.5-coder:14b`, or another Ollama coding model.
