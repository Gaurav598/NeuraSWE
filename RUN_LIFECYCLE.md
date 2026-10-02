# Run lifecycle

The backend state machine in `server/app/run_state.py` is authoritative:

```text
QUEUED → PREPARING → ANALYZING → PLANNING → IMPLEMENTING → VALIDATING
       → AWAITING_APPROVAL → PR_CREATING → COMPLETED
```

`CHANGES_REQUESTED` returns to `QUEUED`. `REJECTED`, `FAILED`, `CANCELLED` and
`TIMED_OUT` are terminal. Legacy `RUNNING`, `SOLVED` and `TIMEOUT` values remain readable
for non-destructive migration. Invalid transitions raise rather than silently overwrite.

On claim, a worker stores its identity, attempt, heartbeat and lease expiration. Every
step verifies ownership. Heartbeats renew the lease. Worker startup and a bounded periodic
recovery pass find expired leases:
idempotent pre-publication phases return to `QUEUED`; `PR_CREATING` is reconciled against
GitHub; cancellation intent becomes `CANCELLED`. A stale worker cannot finalize after its
identity changes.

Cancellation first persists `cancellation_requested_at` and `CANCELLED`. Runtime polling
cancels active provider/tool tasks, local process groups are killed, Docker containers
are stopped, no later tool starts, and worker/state checks prevent late completion.

Every realtime event has a per-run monotonic sequence and is persisted in `run_events`.
Clients replay missed events via HTTP and refresh the authoritative run record.
