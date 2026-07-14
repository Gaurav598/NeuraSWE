# NeuraSWE Production Readiness Runbook

## Current Scope

This runbook covers the GitHub issue to branch to pull request flow. Jira and
ClickUp ticket ingestion should be added as separate connectors that create the
same internal run records.

## Required Inputs

- `GITHUB_PAT` for local testing, or GitHub App credentials for organization production.
- `GITHUB_WEBHOOK_SECRET` for production GitHub webhook verification.
- `GITHUB_DEFAULT_BASE_BRANCH`, usually `main`.
- `LLM_PROVIDER=openai-compatible`, `LLM_API_KEY`, `LLM_MODEL=llama-3.3-70b-versatile`, and `LLM_BASE_URL=https://api.groq.com/openai/v1` for production agent reasoning.
- `OLLAMA_URL`, `OLLAMA_EMBED_MODEL`, and `OLLAMA_EMBED_CONCURRENCY=1` for embeddings.
- Docker access for sandbox containers.
- Repository permission to clone, push branches, open PRs, and comment on issues.

## Verified Local Commands

```bash
docker build -t neuraswe-server-demo ./server
docker run --rm neuraswe-server-demo pytest -q
docker compose up -d --build server worker
curl -fsS http://localhost:3001/api/health
```

`/api/health` must report `agent_llm=true` before running production jobs. With
`LLM_PROVIDER=openai-compatible`, this requires `LLM_API_KEY` to be set in the
server and worker environments.

## GitHub E2E Flow

1. Connect repository from the dashboard or `POST /api/repositories`.
2. Reindex the repository and wait for `index_status=READY`.
3. Trigger with an existing GitHub issue via `POST /api/runs/manual`.
4. Watch the run in the dashboard.
5. Review the PR in GitHub.
6. Merge only in GitHub after review; NeuraSWE does not merge.

## Production Guards Now Present

- Manual issue runs fetch real GitHub issue title/body instead of placeholders.
- Production webhooks reject unsigned payloads when `GITHUB_WEBHOOK_SECRET` is missing.
- Chroma and Python client versions are pinned together.
- NumPy is pinned below 2 for Chroma compatibility.
- Embedding concurrency is configurable and defaults to `1`.
- Large code chunks are split before embedding to avoid Ollama 500s.
- PR creation fails fast if the patch cannot apply.
- PR creation fails fast if no commit is created.
- Run status becomes `FAILED` if the agent solved but PR creation failed.
- PR branches include a run suffix to avoid branch collisions.
- The agent supports `LLM_PROVIDER=openai-compatible` for JSON-mode action output.
- The parser accepts both legacy `THOUGHT/ACTION` text and JSON-mode action objects.
- The runtime fails fast when a model repeatedly emits unparsable actions or unsupported tools.
- Baseline test failures are reported as pre-existing blockers instead of misleading `0 failing`.
- `submit_solution` can open a review PR when final tests still fail only because baseline tests already failed before the change.

## Remaining External Work

- Create GitHub App for organization-grade access instead of a PAT.
- Add Jira connector and ClickUp connector.
- Add deployment secrets in the chosen hosting environment.
- Configure persistent Postgres, Redis, and Chroma volumes/backups.
- Add monitoring for queue failures, PR creation failures, and Ollama errors.
- Add spend/rate-limit monitoring for hosted LLM usage.
