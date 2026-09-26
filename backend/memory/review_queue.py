"""Persistent contradiction review queue (TRD §3 ``contradiction_flags``).

Detection alone isn't enough — PRD G3 wants the system to *ask* instead of
silently trusting either source, and PRD §10 explicitly requires an
explicit accept. So detected conflicts are persisted here as PENDING rows
until the user resolves them:

  * ``accept`` — the proposed value is written to the graph and the old
    fact's validity window is closed (close-old / insert-new, never a
    hard overwrite).
  * ``reject`` — the queue row is marked REJECTED; the graph is untouched.

Rows are also seeded directly from ``10-seed-data.md`` so the review queue
demonstrates the feature on real conflicts on first run.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend.config import settings
from backend.memory.graph import TemporalGraph, _dates_overlap

# Multi-valued predicates: several active values are expected, not a conflict.
_MULTI_VALUED = {"check_in", "milestone", "owns_goal", "tag", "purpose_tag"}

REJECTED = "REJECTED"
ACCEPTED = "ACCEPTED"
PENDING = "PENDING"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ReviewQueue:
    """JSON-backed list of contradiction flags awaiting a human decision."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else Path(settings.review_queue_path)

    # ── persistence ──────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── queries ──────────────────────────────────────────────────────

    def list(self, status: str | None = PENDING) -> list[dict]:
        items = self._load()
        if status and status.upper() != "ALL":
            items = [i for i in items if i.get("status") == status.upper()]
        items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
        return items

    def get(self, item_id: str) -> dict | None:
        for item in self._load():
            if item.get("id") == item_id:
                return item
        return None

    def stats(self) -> dict:
        items = self._load()
        return {
            "pending": sum(1 for i in items if i.get("status") == PENDING),
            "accepted": sum(1 for i in items if i.get("status") == ACCEPTED),
            "rejected": sum(1 for i in items if i.get("status") == REJECTED),
            "total": len(items),
        }

    # ── enqueue ──────────────────────────────────────────────────────

    def add(
        self,
        *,
        subject: str,
        predicate: str,
        existing_value: str,
        proposed_value: str,
        document_id: str | None = None,
        profile_table: str = "user_profile",
        status: str = PENDING,
    ) -> dict | None:
        """Add a flag; dedupes identical PENDING rows. Returns None if dup."""
        if str(existing_value).strip() == str(proposed_value).strip():
            return None
        items = self._load()
        for item in items:
            if (
                item.get("subject") == subject
                and item.get("predicate") == predicate
                and item.get("existing_value") == existing_value
                and item.get("proposed_value") == proposed_value
                and item.get("status") == PENDING
            ):
                return None
        row = {
            "id": f"cf_{uuid.uuid4().hex[:16]}",
            "subject": subject,
            "predicate": predicate,
            "profile_table": profile_table,
            "profile_field": predicate,
            "existing_value": existing_value,
            "proposed_value": proposed_value,
            "document_id": document_id,
            "status": status,
            "created_at": _now(),
            "resolved_at": None,
            "resolution": None,
        }
        items.append(row)
        self._save(items)
        return row

    # ── detection sync ───────────────────────────────────────────────

    def sync(self, graph: TemporalGraph) -> int:
        """Scan the graph for overlapping contradictory facts; enqueue new ones.

        Returns the number of rows actually added.
        """
        from backend.memory.profile import USER_ID, ProfileStore

        profile = ProfileStore(graph)
        active = [
            f for f in graph.query_all_facts()
            if not f.get("superseded_by")
            and f.get("object_literal") is not None
            and f.get("predicate") not in _MULTI_VALUED
        ]
        groups: dict[tuple[str, str], list[dict]] = {}
        for fact in active:
            groups.setdefault(
                (fact.get("subject", ""), fact.get("predicate", "")), []
            ).append(fact)

        added = 0
        for (subject, predicate), facts in groups.items():
            if len(facts) < 2:
                continue
            revealed = []
            for fact in facts:
                raw = fact.get("object_literal") or ""
                value = (
                    profile._reveal(predicate, raw) if subject == USER_ID else raw
                )
                revealed.append((value, fact))
            for i in range(len(revealed)):
                for j in range(i + 1, len(revealed)):
                    va, fa = revealed[i]
                    vb, fb = revealed[j]
                    if va == vb:
                        continue
                    if not _dates_overlap(
                        fa.get("valid_from"), fa.get("valid_to"),
                        fb.get("valid_from"), fb.get("valid_to"),
                    ):
                        continue
                    # existing = the older recorded value, proposed = newer
                    older, newer = (fa, fb) if (
                        fa.get("recorded_at") or ""
                    ) <= (fb.get("recorded_at") or "") else (fb, fa)
                    old_val = profile._reveal(predicate, older.get("object_literal") or "") \
                        if subject == USER_ID else (older.get("object_literal") or "")
                    new_val = profile._reveal(predicate, newer.get("object_literal") or "") \
                        if subject == USER_ID else (newer.get("object_literal") or "")
                    row = self.add(
                        subject=subject,
                        predicate=predicate,
                        existing_value=old_val,
                        proposed_value=new_val,
                        document_id=None,
                        profile_table="user_profile" if subject == USER_ID else subject,
                    )
                    if row:
                        added += 1
        return added

    # ── resolution ───────────────────────────────────────────────────

    def resolve(
        self,
        item_id: str,
        *,
        accept: bool,
        value: str | None = None,
        graph: TemporalGraph | None = None,
    ) -> dict:
        """Accept or reject a proposed value. Accept mutates the graph."""
        item = self.get(item_id)
        if item is None:
            raise KeyError(f"Unknown contradiction: {item_id}")
        if item.get("status") != PENDING:
            raise ValueError(f"Contradiction already {item.get('status')}")

        if accept:
            if graph is None:
                raise ValueError("graph is required to accept a contradiction")
            new_value = (value if value is not None else item.get("proposed_value") or "").strip()
            if not new_value:
                raise ValueError("proposed value is empty")

            from backend.memory.profile import USER_ID, ProfileStore

            subject = item.get("subject", "")
            predicate = item.get("predicate", "")
            profile = ProfileStore(graph)
            protect = profile._protect if subject == USER_ID else (lambda _f, v: v)
            reveal = profile._reveal if subject == USER_ID else (lambda _f, v: v)

            # Close every active value that differs from the accepted one —
            # the recorded "existing" may be stale or phrased differently
            # from what is currently stored.
            to_close: list[dict] = []
            for fact in graph.query_all_facts(entity=subject):
                if fact.get("subject") != subject or fact.get("superseded_by"):
                    continue
                if fact.get("predicate") != predicate:
                    continue
                raw = fact.get("object_literal")
                if raw is None:
                    continue
                current = reveal(predicate, raw) if subject == USER_ID else raw
                if current != new_value:
                    to_close.append(fact)

            new_fact_id = graph.add_fact(
                subject,
                predicate,
                object_literal=protect(predicate, new_value),
                valid_from=_now(),
                source_episode_id="contradiction_resolve",
            )
            for fact in to_close:
                graph.supersede_fact(fact["fact_id"], new_fact_id)
            item["resolution"] = ACCEPTED
            item["applied_value"] = new_value
        else:
            item["resolution"] = REJECTED

        item["status"] = ACCEPTED if accept else REJECTED
        item["resolved_at"] = _now()

        items = self._load()
        for i, row in enumerate(items):
            if row.get("id") == item_id:
                items[i] = item
                break
        self._save(items)
        return item
