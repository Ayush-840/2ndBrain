#!/usr/bin/env bash
# Weekly audit — full lint, flag issues, generate focus list
# Runs every Sunday at 9:00 AM
set -euo pipefail

VAULT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VAULT_DIR"

echo "[$(date)] Starting weekly audit..."

claude -p "Audit the entire wiki. Walk every folder and article. Flag: conflicting claims, dead links, missing articles that are referenced but don't exist, topics worth opening up, and any inconsistencies. Don't edit — just write a report to output/weekly-audit-$(date +%Y-%m-%d).md with a prioritized focus list for next week."

echo "[$(date)] Weekly audit complete."
