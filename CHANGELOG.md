# Changelog

## Reliability and security upgrade

- Added production fail-closed sandbox selection, dedicated Compose sandbox daemon,
  non-root/capability/read-only/resource policies, network cutoff, bounded output and
  cancellation cleanup.
- Centralized canonical workspace validation and schema/permission checked tools.
- Added bearer principals, repository/run ownership and authorized Socket.IO rooms.
- Added webhook delivery idempotency and stricter Jira/GitHub authentication.
- Added authoritative lifecycle transitions, state versions, cancellation intent, worker
  leases/heartbeats, orphan recovery and sequenced durable events.
- Replaced automatic PR creation with patch review and approve/reject/request-changes.
- Added deterministic branch reconciliation, PR idempotency and patch secret checks.
- Added verification classifications/test identity comparison, retrieval deduplication,
  path ranking/context budgets and indexing error/progress fields.
- Removed private reasoning from persisted/realtime dashboard data; added review evidence,
  approval controls, PR state and reconnect replay.
- Added safe database migration, focused tests, controlled benchmark runner and operational
  documentation. Full Docker/integration/E2E validation remains a user handoff task.
