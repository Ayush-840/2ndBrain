#!/usr/bin/env bash
# Nightly review — refresh indexes, log gaps, catch missed cross-links
# Runs every night at 11:00 PM
set -euo pipefail

VAULT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VAULT_DIR"

echo "[$(date)] Starting nightly review..."

claude -p "Review the wiki: refresh all topic _index.md files to match actual articles, check that _master-index.md is current, identify any broken [[wiki links]] or missing cross-links, and log gaps to output/nightly-review-$(date +%Y-%m-%d).md."

echo "[$(date)] Nightly review complete."
