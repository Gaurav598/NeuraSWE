# Human review and publication

A validated patch enters `AWAITING_APPROVAL` with its unified diff, modified files,
baseline/final verification, unexecuted tests, risks/limitations and provider-reported
token count where available (otherwise explicitly labeled prompt estimate).
Only the run owner can act.

- `APPROVE` atomically records approval and enters `PR_CREATING`.
- `REJECT` enters terminal `REJECTED` without external changes.
- `REQUEST_CHANGES` records the comment and queues a new implementation attempt.

PR publication uses `neuraswe/run-<run-id>-v<attempt>` and persists branch, commit, PR number, URL
and status. Repeated approval is idempotent. Before creation—and after ambiguous network
failure—the worker queries GitHub for an existing PR from that branch. Patch safety,
non-empty diff and base-branch application are rechecked. A failed publication returns to
review and can be retried. NeuraSWE never merges the PR.

`UNATTENDED_PR_PUBLICATION` is disabled by default and the current HTTP workflow does not
enable it; operators must implement a separately reviewed policy before using such a mode.
