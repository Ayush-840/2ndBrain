"""Append-only access audit log (feature extensions §4).

Every query, document view and profile edit gets one JSON line:
``who / what / when``. Append-only by construction — there is no update
or delete path, which is the whole point of an audit trail.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.config import settings


def record(
    action: str,
    *,
    target_id: str | None = None,
    query_text: str | None = None,
    detail: str | None = None,
    actor: str = "owner",
    path: Path | str | None = None,
) -> dict:
    """Append one audit entry. Never raises (audit failures must not break requests)."""
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "action": action,
        "actor": actor,
        "target_id": target_id,
        "query_text": query_text,
        "detail": detail,
    }
    try:
        log_path = Path(path) if path else Path(settings.audit_log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return entry


def read(
    *,
    limit: int = 100,
    action: str | None = None,
    path: Path | str | None = None,
) -> list[dict]:
    """Return the newest entries first (optionally filtered by action)."""
    log_path = Path(path) if path else Path(settings.audit_log_path)
    if not log_path.exists():
        return []
    entries: list[dict] = []
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if action and entry.get("action") != action:
                    continue
                entries.append(entry)
    except OSError:
        return []
    entries.reverse()
    return entries[: max(0, limit)]


def count(path: Path | str | None = None) -> int:
    log_path = Path(path) if path else Path(settings.audit_log_path)
    if not log_path.exists():
        return 0
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0
