# Solve your first real issue with NeuraSWE (Docker Compose)

Goal: get one GitHub issue auto-fixed end-to-end (issue → branch → PR) without
dying on Groq's free-tier limit. The trick is two-fold: **shrink token usage per
run**, and **add Gemini as a free fallback** so a throttled Groq never kills a run.

---

## Why Groq "worked then stopped"

Groq's free tier isn't blocked by requests/min — it's the **daily token budget
(~100K tokens/day)**. The ReAct loop resends the growing trajectory every step,
so one or two full runs drains the day and everything returns HTTP 429.

Two fixes, both already supported by the code:
1. **Use fewer tokens per run** (fewer steps, smaller context).
2. **Chain a free fallback** (Gemini 2.0 Flash = ~1M tokens/min free). When Groq
   429s, the agent transparently continues on Gemini instead of failing.

> A bug was just fixed in `docker-compose.yml`: the `server`/`worker` containers
> now load the full `.env` (`env_file: .env`), so `GEMINI_API_KEY` and the
> `AGENT_*` tuning vars actually reach the agent. Before this, the fallback chain
> was invisible inside Docker and runs died at the Groq limit.

---

## Step 1 — Grab a free Gemini key (2 minutes, no card)

https://aistudio.google.com/apikey → "Create API key" → copy it.

## Step 2 — Write your `.env`

From the `neuraswe/` folder:

```bash
cp .env.example .env
```

Then set these values (Groq stays primary for quality; Gemini is the safety net):

```bash
# --- GitHub (needs a PAT with the `repo` scope to push branches + open PRs) ---
GITHUB_PAT=ghp_your_token_here
GITHUB_DEFAULT_BASE_BRANCH=main          # change if your repo's default isn't main

# --- Primary model: Groq. You can list MULTIPLE keys, comma-separated, to
#     multiply your daily budget — the client rotates when one is throttled. ---
LLM_PROVIDER=openai-compatible
LLM_API_KEY=gsk_key1,gsk_key2            # 1+ Groq keys (free accounts are fine)
LLM_MODEL=llama-3.3-70b-versatile
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_REQUESTS_PER_MINUTE=15

# --- Free fallback: Gemini (huge limits). This is what stops runs from dying. ---
LLM_FALLBACK_ENABLED=true
GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-2.0-flash

# --- Shrink token usage so a run fits the daily budget ---
AGENT_MAX_STEPS=10
AGENT_MAX_CONTEXT_TOKENS=4000
AGENT_FULL_TRAJECTORY_STEPS=6
```

> If Groq keeps throttling and you don't care which model fixes it, make Gemini
> the **primary** instead — it almost never rate-limits:
> `LLM_MODEL=gemini-2.0-flash` and
> `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`
> and put the Gemini key in `LLM_API_KEY`.

## Step 3 — Build the sandbox image (required!)

The worker spawns a sibling container per issue. If this image is missing, every
run fails immediately:

```bash
bash scripts/build-sandbox.sh
```

## Step 4 — Bring up the stack

```bash
docker compose up -d postgres redis chromadb ollama
docker compose exec ollama ollama pull nomic-embed-text   # for semantic search (small, optional)
docker compose up -d server worker client
docker compose logs -f worker                              # watch the agent here
```

Check health: open http://localhost:3001/api/health — `database`, `redis`,
`chromadb` should be `true`. (`ollama` can be `false` if you skipped the model
pull; the agent falls back to `grep` for code search.)

## Step 5 — Connect your repo and trigger a run

1. Open the dashboard: http://localhost:5173 → **Repositories**.
2. Connect `your-username/your-repo`. Indexing starts automatically.
3. Either:
   - Type an existing **issue number** and hit **Run**, **or**
   - On GitHub, label an issue `neuraswe` (if you wired the webhook).
4. Open the run and watch THINK → ACT → OBSERVE stream live.

---

## Pick a first issue that WILL succeed

The agent only "wins" if it can prove the fix with tests. For your first run,
choose an issue where:

- The repo has a **runnable test suite** the sandbox can detect
  (`npm test`, `pytest`, `go test`, or `mvn test`).
- The bug is **small and local** — a wrong operator, an off-by-one, a bad regex,
  a missing null check. Avoid anything needing cross-service setup or secrets.
- There's an **existing failing test**, or the bug is trivial to pin with one.
- The issue body is **specific**: describe the wrong behavior and, if you can,
  name the file/function. Example that works well:
  > "`parse_duration()` in `utils/time.py` returns seconds instead of
  > milliseconds for inputs like `'1m'`. Expected 60000, got 60."

If your repo has no tests, add one tiny failing test first (the agent will then
have a target to satisfy) — or tell me and I'll generate a minimal demo repo you
can fork in 30 seconds.

---

## If a run still struggles

| Symptom | Fix |
|--------|-----|
| Run fails instantly | Sandbox image not built → `bash scripts/build-sandbox.sh` |
| "All LLM providers failed" / 429 | Add the Gemini key (Step 2); confirm `docker compose config` shows it under `worker` |
| Agent loops without editing | Issue too vague or repo too big → pick a smaller, clearly-scoped issue |
| `submit_solution` refused | Tests are failing — that's correct behavior; the bug needs a different fix |
| No PR created | PAT missing `repo` scope, or base branch isn't `main` (set `GITHUB_DEFAULT_BASE_BRANCH`) |
| Tests "not detected" | The sandbox image lacks your toolchain — add it to `server/Dockerfile.sandbox` and rebuild |

Verify the fallback wiring actually landed in the containers:

```bash
docker compose config | grep -A2 GEMINI_API_KEY
docker compose exec worker printenv | grep -E "GEMINI|AGENT_MAX_STEPS|LLM_"
```

You should see `GEMINI_API_KEY` and `AGENT_MAX_STEPS=10` printed.
```
