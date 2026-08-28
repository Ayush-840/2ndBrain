#!/usr/bin/env bash
# Daily ingest — sweep raw/ into wiki
# Runs every morning at 7:00 AM
set -euo pipefail

VAULT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VAULT_DIR"

echo "[$(date)] Starting daily ingest..."

if [ -z "$(ls -A raw/ 2>/dev/null)" ]; then
  echo "[$(date)] Nothing in raw/. Skipping."
  exit 0
fi

claude -p "Compile everything in raw/. For each file: read it, pick or create a topic in wiki/, write a tight article with key takeaways, drop in [[wiki links]] to related ideas, then update both the topic index and the master index. Cross-link aggressively."

echo "[$(date)] Daily ingest complete."
