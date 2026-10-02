# NeuraSWE architecture

NeuraSWE separates its trusted control plane from repository execution. FastAPI owns
authentication, repository/run authorization, durable state and review decisions.
arq workers own leases for long-running work. ChromaDB stores code chunks; PostgreSQL
stores authoritative run state and ordered events; Redis carries jobs and Socket.IO
messages. The React application always reconciles with HTTP state after realtime events.

The lifecycle is: issue ingestion → authorized repository lookup → indexed retrieval →
lease-owned agent loop → verification comparison → `AWAITING_APPROVAL` → explicit review
→ idempotent branch/PR creation. PR creation is not part of issue solving and no code is
merged automatically.

In Compose, only the worker can reach the internal `sandbox-daemon` Docker-in-Docker
service. The API has no Docker socket. Each run gets a non-root container with dropped
capabilities, no-new-privileges, read-only root, bounded writable tmpfs, CPU/memory/PID,
timeout and output limits. Bootstrap networking used for clone is disconnected before
repository commands when `SANDBOX_NETWORK_MODE=none`.

Authentication is a deliberately small bearer-token boundary (`AUTH_TOKENS=token=user`).
It can be replaced by an OIDC adapter while retaining stable `owner_id` checks. GitHub
and Jira webhooks have independent signature/secret and delivery-id boundaries.
The bundled SPA token is appropriate only for a controlled single-user deployment;
multi-user production requires an identity provider/session exchange rather than a token
compiled into static assets.
GitHub webhook routing also requires a unique connected repository ownership record;
shared-repository multi-tenant routing needs a first-class installation/account model.

The current retrieval system intentionally remains vector search rather than Graph RAG.
It performs filtered indexing, incremental changed-file replacement, deduplication,
path-aware ranking and a bounded retrieval budget.
