# Sandbox security

## Trust boundaries

The API, database and queue are trusted control-plane components. Issue text, repository
content, dependency scripts, build output, model output and generated patches are
untrusted. Only the worker can request isolated execution. No integration or LLM secrets
are injected into sandbox containers.

Production fails closed if Docker support, the configured daemon, image, network
disconnect or container creation is unavailable. `SANDBOX_USE_LOCAL=true` additionally
requires `SANDBOX_ALLOW_UNSAFE_LOCAL=true` and is rejected when `NODE_ENV=production`.
Local mode uses a scrubbed environment but remains unsafe and development-only.

## Container policy

Sandboxes run as UID/GID 1000, drop all Linux capabilities, enable no-new-privileges,
use a read-only root filesystem, and receive only bounded tmpfs workspace/tmp storage.
Memory, CPU, PID, command timeout and captured output are bounded. Containers are stopped
on normal completion, error, timeout and cancellation. Canonical path checks prevent
absolute paths, traversal and symlink escape for filesystem tools.

With the default `SANDBOX_NETWORK_MODE=none`, temporary bootstrap networking permits the
trusted clone operation and is then forcibly disconnected before dependency scripts,
tests or generated commands execute. Set `bridge` only when a reviewed workload requires
egress; it provides unrestricted container egress and is a documented risk.

## Dedicated daemon

Compose uses an internal Docker-in-Docker daemon. This removes the host Docker socket
from the API and worker. The daemon itself is privileged and is therefore a dedicated
security boundary, not a claim of perfect isolation. Production operators should place
it on a separate VM/node or replace it with a hardened microVM/gVisor executor.

Build its image after the daemon is healthy:

```bash
docker compose run --rm worker python -m app.sandbox.build_image
```

Known limitations: Docker daemon compromise can control resources inside that dedicated
daemon; network allowlisting is binary (`none` or configured Docker mode), not domain-
aware; disk quota relies on bounded tmpfs and daemon storage operations. Cancelling during
an already-started GitHub push can leave a deterministic remote branch; the run records an
ambiguous publication state and a subsequent approved retry reconciles before creating a PR.
