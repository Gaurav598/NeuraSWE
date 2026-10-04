# HTTP API and realtime events

When `AUTH_REQUIRED=true`, application endpoints require `Authorization: Bearer <token>`.
Tokens map to stable owners through `AUTH_TOKENS=token=user`. Webhooks use their own
authentication. Unauthorized private objects return 404.

Key endpoints:

- `GET/POST /api/repositories`, `POST /api/repositories/{id}/reindex`
- `GET /api/repositories/{id}/issues`
- `POST /api/runs/manual`, `GET /api/runs`, `GET /api/runs/{id}`
- `POST /api/runs/{id}/stop`
- `POST /api/runs/{id}/review` with `APPROVE`, `REJECT`, or `REQUEST_CHANGES`
- `GET /api/runs/{id}/events?after_sequence=N` for replay
- `POST /api/webhook/github`, `POST /api/webhook/jira`

GitHub webhook deliveries resolve to an existing connected repository ownership record.
Production does not create authorization records from webhook payloads, and ambiguous
multi-owner matches are rejected.

Socket.IO clients authenticate with `{auth: {token}}`, then emit `subscribe` with a
`run_id`. The server checks ownership before joining `run:<id>`. Events include `run_id`
and monotonic `sequence`: `run:status`, `agent:step`, `run:review`, and `run:complete`.
Clients deduplicate by sequence, replay persisted gaps, and refetch `/api/runs/{id}`;
Socket.IO is never the source of truth.

GitHub requires `X-Hub-Signature-256`, event type, and `X-GitHub-Delivery`. Jira requires
the configured secret and, in production, `X-Atlassian-Webhook-Identifier`. Duplicate
delivery IDs return without creating another run.
