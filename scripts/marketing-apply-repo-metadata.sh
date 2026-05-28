#!/usr/bin/env bash
# scripts/marketing-apply-repo-metadata.sh
#
# Idempotently sets the marketing surface on the GitHub repo:
#   - Description (≤120 chars, capability-only framing)
#   - Topics (3–10, GitHub topic-discovery surface)
#
# Run from an authenticated `gh` shell (gh auth login first). Safe to re-run;
# `gh api` PATCH/PUT are idempotent on identical payloads. Source of truth for
# the marketing copy is README.md `## Capability` and `## How chrome-bridge compares`.
#
# Provenance: shipped with PR #8 (feat(marketing): hero + capability +
# comparison + demo + OG).

set -euo pipefail

REPO="${REPO:-yolo-labz/chrome-bridge}"

DESCRIPTION="Trusted-event Chrome MV3 automation bridge. Extension + Python relay on 127.0.0.1:9224. Cross-platform."

# 8 topics, GitHub topic-discovery surface. Order does not matter; GitHub stores
# them lowercase + sorted on retrieval.
TOPICS_JSON='{"names":["chrome","mv3","extension","automation","python","relay","claude-code","cross-platform"]}'

echo "→ patching description on ${REPO}"
gh api -X PATCH "repos/${REPO}" -f description="${DESCRIPTION}" --jq '.description'

echo "→ putting topics on ${REPO}"
printf '%s' "${TOPICS_JSON}" | gh api -X PUT "repos/${REPO}/topics" --input - --jq '.names | join(", ")'

echo "✓ done"
