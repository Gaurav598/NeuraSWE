# Local testing guide

These are handoff procedures; they were not executed as part of the implementation pass.

## Start the stack

1. Copy `.env.example` to `.env`; set GitHub, provider, webhook and auth values.
2. Start dependencies: `docker compose up -d postgres redis chromadb ollama sandbox-daemon`.
3. Build the sandbox in its dedicated daemon: `docker compose run --rm worker python -m app.sandbox.build_image`.
4. Start services: `docker compose up -d server worker client`.
5. Expected: `/api/health` reports database/Redis/Chroma and configured models; worker
   logs show startup recovery. Failure signs: migration errors, missing sandbox image,
   Redis connection errors. Sources: `server/app/main.py`, `server/app/queue/worker.py`.

For local processes, install `server/requirements.txt`, run `alembic upgrade head`, then
`uvicorn app.main:app --port 3001`, `arq app.queue.worker.WorkerSettings`, and in `client`,
`npm install && npm run dev`. Host execution requires both sandbox local flags and is
never permitted in production.

## GitHub and provider

Set `GITHUB_PAT` or App credentials, a webhook secret, and an accessible test repository.
Set one provider credential/model; comma-separated credential rotation is ignored. Connect
the test repository, wait for `READY`, and trigger a controlled issue. Expected: phases
advance to `AWAITING_APPROVAL`, no branch/PR exists yet, and the diff/evidence is visible.
Provider/auth errors should become categorized run failures, not infinite retries.

## Review and safe PR test

Review the diff in a disposable repository. Approve once, then repeat approval. Expected:
one deterministic branch and one PR, never a merge. Reject another run and verify no remote
change. Request changes and verify a new worker attempt. Inspect run `pr_status`, branch,
commit, PR URL and worker logs.

## Failure scenarios

- Cancellation: cancel during LLM, shell and tests. Expect `CANCELLED`, process/container
  termination, no later completion.
- Worker restart: stop the worker, wait beyond `WORKER_LEASE_SECONDS`, restart. Expect safe
  phases to requeue and publication to reconcile without duplicate PRs.
- Docker unavailable: stop `sandbox-daemon`. Production must fail the run; it must not run
  on the worker/server filesystem.
- Fail-closed local mode: set `NODE_ENV=production SANDBOX_USE_LOCAL=true
  SANDBOX_ALLOW_UNSAFE_LOCAL=true`. Sandbox creation must reject it.
- Traversal: invoke file tools with `../`, `/etc/passwd`, and a workspace symlink to an
  external file. Expect controlled errors and no read/write.
- Duplicate webhook: resend the same delivery header and body. Expect one run.
- Socket reconnect: disconnect/reconnect while running. Expect replay without duplicate
  events and HTTP-refreshed final state.

## Verification and benchmark

Run focused checks: `cd server && python -m pytest tests/test_workspace_security.py
tests/test_run_state.py tests/test_tool_permissions.py tests/test_verification.py
tests/test_patch_safety.py`. Run frontend compilation with `cd client && npm run build`.
Copy `benchmarks/cases.example.json`, point it at controlled repositories, then run
`python benchmarks/runner.py --cases ... --output ...`. Expect JSON outcomes; do not
interpret them as SWE-bench scores.
