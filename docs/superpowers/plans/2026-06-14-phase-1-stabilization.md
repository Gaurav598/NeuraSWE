# Phase 1 Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing NeuraSWE GitHub issue flow buildable, runnable, and locally verifiable before adding Jira/ClickUp.

**Architecture:** Keep the current FastAPI, worker, Docker Compose, and React dashboard architecture intact. Apply minimal compatibility, hygiene, and runbook changes only; do not add new ticket-source behavior in this phase.

**Tech Stack:** FastAPI, SQLAlchemy, arq, Redis, PostgreSQL, ChromaDB, Docker Compose, React, Vite.

---

### Task 1: Dependency Compatibility

**Files:**
- Modify: `server/requirements.txt`
- Test: Docker backend image build

- [ ] **Step 1: Pin Redis to an arq-compatible version**

Set `redis==4.6.0` because `arq==0.26.0` requires `redis<5`.

- [ ] **Step 2: Build backend image**

Run: `docker build -t neuraswe-server-demo ./server`
Expected: image builds successfully.

### Task 2: Redis Health Compatibility

**Files:**
- Modify: `server/app/api/health.py`
- Test: `server/tests/test_health.py`

- [ ] **Step 1: Add tests for Redis 4 and Redis 5 close APIs**

Create tests that verify `_close_redis_client` uses `aclose()` when available and falls back to `close()` otherwise.

- [ ] **Step 2: Implement helper**

Add `_close_redis_client(client)` and call it from `_check_redis()`.

- [ ] **Step 3: Run backend tests**

Run: `docker run --rm -e SANDBOX_USE_LOCAL=true neuraswe-server-demo pytest -q`
Expected: all tests pass.

### Task 3: Docker Build Hygiene

**Files:**
- Create: `server/.dockerignore`
- Create: `client/.dockerignore`
- Modify: `.gitignore` if needed

- [ ] **Step 1: Exclude generated and local-only files from build contexts**

Ignore `__pycache__`, `.pyc`, virtualenvs, node modules, build output, logs, and env files.

- [ ] **Step 2: Remove generated Python bytecode from workspace**

Run: `find server -name '__pycache__' -type d -prune -exec rm -rf {} +` and `find server -name '*.pyc' -delete`.

### Task 4: Local Demo Runbook

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document minimal dashboard demo path**

Add commands for starting Postgres/Redis/Chroma, backend, seeding demo data, and starting the dashboard.

- [ ] **Step 2: Document full agent requirements**

Call out Ollama model pull, sandbox image build, GitHub credentials, and worker service as required for full end-to-end PR testing.
