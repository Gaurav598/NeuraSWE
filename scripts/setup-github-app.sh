#!/usr/bin/env bash
# Interactive helper to point a GitHub App / webhook at your local NeuraSWE.
set -euo pipefail

cat <<'TXT'
NeuraSWE GitHub setup
====================

1. Create a GitHub App (Settings → Developer settings → GitHub Apps → New):
   - Webhook URL: <your tunnel>/api/webhook/github
   - Webhook secret: set GITHUB_WEBHOOK_SECRET to the same value in .env
   - Permissions: Issues (Read/Write), Pull requests (Read/Write), Contents (Read/Write)
   - Subscribe to events: Issues
   - Download the private key (.pem) → set GITHUB_PRIVATE_KEY_PATH
   - Note the App ID → set GITHUB_APP_ID

2. Install the App on a test repository.

3. Start a webhook tunnel, e.g.:
   npx smee -u https://smee.io/YOUR_CHANNEL -t http://localhost:3001/api/webhook/github

4. Create an issue and add the label "neuraswe" to trigger a run.

Quick alternative (no App): set GITHUB_PAT in .env and trigger runs from the
dashboard's Repositories page.
TXT
