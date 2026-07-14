#!/usr/bin/env bash
# Build the sandbox image the agent runs code inside.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t neuraswe-sandbox:latest -f server/Dockerfile.sandbox server
echo "Built neuraswe-sandbox:latest"
