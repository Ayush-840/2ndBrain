"""Personal profile engine over the temporal graph.

Represents the structured side of the second brain (research paper §2.1):
identity, education, family, goals and timeline — all stored as entities
and facts in :class:`~backend.memory.graph.TemporalGraph`, so every field
gets the same bi-temporal semantics the rest of the system uses:

  * ``set_field`` never overwrites — it closes the old fact's validity
    window (close-old / insert-new, TRD §7 "Data integrity").
  * ``history`` can answer "what was my address before I moved".
  * contradictions surface through the review queue instead of silently
    mutating structured facts (PRD §10 open question 1).

Sensitive fields (government IDs, financials — see
``settings.sensitive_profile_fields``) are encrypted at the application
boundary with the same Fernet key material the document blob store uses,
so a raw graph dump never exposes them in plaintext.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from backend.config import settings
from backend.memory.blob_store import _derive_fernet_key, _is_fernet_key
from backend.memory.graph import TemporalGraph

USER_ID = "user"
_ENC_PREFIX = "enc:v1:"
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _short_hash(text: str) -> str:
    """Deterministic id suffix (str.hash() is randomized per process)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _slug(text: str, *, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:max_len] or "x"


class ProfileStore:
    """Structured profile CRUD built on the temporal graph."""

    def __init__(self, graph: TemporalGraph, *, key: str | None = None):
        self._graph = graph
        secret = key if key is not None else settings.blob_key
        if _is_fernet_key(secret):
            self._fernet_key = secret.encode()
        else:
            self._fernet_key = _derive_fernet_key(secret) if secret else _derive_fernet_key(
                "2ndbrain-local-profile-key"
            )
        self._sensitive = settings.sensitive_fields

    # ── Field-level encryption (PRD G5 / extensions §4) ──────────────

    def _protect(self, field: str, value: str) -> str:
        if field not in self._sensitive or not value:
            return value
        from cryptography.fernet import Fernet

        token = Fernet(self._fernet_key).encrypt(value.encode()).decode()
        return f"{_ENC_PREFIX}{token}"

    def _reveal(self, field: str, stored: str) -> str:
        if not stored.startswith(_ENC_PREFIX):
            return stored
        from cryptography.fernet import Fernet, InvalidToken

        try:
            return Fernet(self._fernet_key).decrypt(
                stored[len(_ENC_PREFIX):].encode()
            ).decode()
        except InvalidToken:
            return "[encrypted — key mismatch]"

    # ── Identity / education fields (bi-temporal) ────────────────────

    def ensure_user(self) -> str:
        self._graph.add_entity(USER_ID, "User", "person")
        return USER_ID

    def _edge_exists(
        self,
        subject: str,
        predicate: str,
        *,
        object_id: str | None = None,
        literal: str | None = None,
    ) -> bool:
        """True when an active fact already says exactly this (idempotent writes)."""
        for fact in self._graph.query_all_facts(entity=subject):
            if fact.get("subject") != subject or fact.get("superseded_by"):
                continue
            if fact.get("predicate") != predicate:
                continue
            if object_id is not None and fact.get("object") == object_id:
                return True
            if literal is not None and fact.get("object_literal") == literal:
                return True
        return False

    def _set_literal(self, subject: str, predicate: str, value: str) -> dict:
        """Supersede-and-add, but a no-op when the value is already current."""
        if self._edge_exists(subject, predicate, literal=value):
            for fact in self._graph.query_all_facts(entity=subject):
                if (
                    fact.get("subject") == subject
                    and fact.get("predicate") == predicate
                    and fact.get("object_literal") == value
                    and not fact.get("superseded_by")
                ):
                    return {
                        "new_fact_id": fact.get("fact_id"),
                        "superseded": [],
                        "unchanged": True,
                    }
        return self._graph.supersede_and_add(
            subject, predicate, object_literal=value, valid_from=_now()
        )

    def _set_link(self, subject: str, predicate: str, object_id: str) -> dict:
        """Entity-to-entity edge; no-op when the link already exists."""
        if self._edge_exists(subject, predicate, object_id=object_id):
            return {"new_fact_id": None, "superseded": [], "unchanged": True}
        return self._graph.supersede_and_add(
            subject, predicate, object_id=object_id, valid_from=_now()
        )

    def set_field(
        self,
        field: str,
        value: str,
        *,
        confidence: float = 1.0,
        source: str = "user",
    ) -> dict:
        """Set a profile field, superseding any active prior value."""
        field = field.strip().lower()
        if not _FIELD_RE.match(field):
            raise ValueError(f"Invalid field name: {field!r}")
        if value is None or str(value).strip() == "":
            raise ValueError("Value must be non-empty")
        self.ensure_user()
        stored = self._protect(field, str(value).strip())
        if self._edge_exists(USER_ID, field, literal=stored):
            current = self.get_field(field)
            if current == str(value).strip():
                return {
                    "new_fact_id": None,
                    "superseded": [],
                    "field": field,
                    "value": current,
                    "unchanged": True,
                }
        result = self._graph.supersede_and_add(
            USER_ID,
            field,
            object_literal=stored,
            valid_from=_now(),
            confidence=confidence,
            source_episode_id=f"profile:{source}",
        )
        result["field"] = field
        result["value"] = str(value).strip()
        return result

    def get_field(self, field: str) -> str | None:
        field = field.strip().lower()
        for fact in self._graph.query_all_facts(entity=USER_ID):
            if fact.get("subject") != USER_ID or fact.get("predicate") != field:
                continue
            if fact.get("superseded_by"):
                continue
            lit = fact.get("object_literal")
            if lit is None:
                continue
            return self._reveal(field, lit)
        return None

    def get_profile(self) -> dict[str, str]:
        """Every active, non-relationship profile field (decrypted)."""
        profile: dict[str, str] = {}
        for fact in self._graph.query_all_facts(entity=USER_ID):
            if fact.get("subject") != USER_ID or fact.get("superseded_by"):
                continue
            lit = fact.get("object_literal")
            if lit is None:
                continue  # object_id facts are relationships, not fields
            field = fact.get("predicate", "")
            profile[field] = self._reveal(field, lit)
        return profile

    def history(self, field: str) -> list[dict]:
        """Bi-temporal history of one field, newest first (PRD G1)."""
        field = field.strip().lower()
        rows: list[dict] = []
        for fact in self._graph.query_all_facts(entity=USER_ID, include_superseded=True):
            if fact.get("subject") != USER_ID or fact.get("predicate") != field:
                continue
            lit = fact.get("object_literal")
            if lit is None:
                continue
            rows.append(
                {
                    "fact_id": fact.get("fact_id"),
                    "value": self._reveal(field, lit),
                    "valid_from": fact.get("valid_from"),
                    "valid_to": fact.get("valid_to"),
                    "superseded_by": fact.get("superseded_by"),
                    "recorded_at": fact.get("recorded_at"),
                    "confidence": fact.get("confidence"),
                    "source_episode_id": fact.get("source_episode_id"),
                }
            )
        rows.sort(key=lambda r: r.get("recorded_at") or "", reverse=True)
        return rows

    # ── Family / contacts as a traversable graph (extensions §1) ─────

    def add_person(
        self,
        name: str,
        relation: str,
        *,
        notes: str = "",
        contact: str = "",
    ) -> str:
        """Model a person as a node + a ``user --relation--> person`` edge."""
        if not name.strip():
            raise ValueError("name is required")
        self.ensure_user()
        rel = _slug(relation, max_len=30)
        pid = f"person_{_slug(name)}_{_short_hash(name)}"
        self._graph.add_entity(pid, name.strip(), "person")
        self._set_link(USER_ID, rel, pid)
        if notes:
            self._set_literal(pid, "notes", notes)
        if contact:
            self._set_literal(pid, "contact", contact)
        return pid

    def relationships(self) -> list[dict]:
        """Edges out of the user node: relation → person."""
        out: list[dict] = []
        for fact in self._graph.query_all_facts(entity=USER_ID):
            if fact.get("subject") != USER_ID or fact.get("superseded_by"):
                continue
            if fact.get("object_literal") is not None:
                continue
            obj = fact.get("object", "")
            if obj.startswith("_literal:") or obj == USER_ID:
                continue
            person = self._graph.get_entity(obj) or {}
            out.append(
                {
                    "person_id": obj,
                    "name": person.get("label", obj),
                    "relation": fact.get("predicate", ""),
                    "since": fact.get("valid_from"),
                    "fact_id": fact.get("fact_id"),
                }
            )
        out.sort(key=lambda r: r["relation"])
        return out

    # ── Goals with check-in history (extensions §1) ──────────────────

    def add_goal(
        self,
        title: str,
        *,
        category: str = "General",
        description: str = "",
        target_date: str | None = None,
    ) -> str:
        if not title.strip():
            raise ValueError("title is required")
        self.ensure_user()
        gid = f"goal_{_slug(title)}_{_short_hash(title)}"
        self._graph.add_entity(gid, title.strip(), "goal")
        self._set_literal(gid, "category", category)
        if not self._edge_exists(gid, "status"):
            self._set_literal(gid, "status", "in_progress")
        if description:
            self._set_literal(gid, "description", description)
        if target_date:
            self._set_literal(gid, "target_date", target_date)
        self._set_link(USER_ID, "owns_goal", gid)
        return gid

    def goal_check_in(self, goal_id: str, percent: int, note: str = "") -> dict:
        """Append a dated progress check-in (never a mutable flag)."""
        if percent < 0 or percent > 100:
            raise ValueError("percent must be 0..100")
        entity = self._graph.get_entity(goal_id)
        if not entity or entity.get("entity_type") != "goal":
            raise KeyError(f"Unknown goal: {goal_id}")
        when = _now()
        fact_id = self._graph.add_fact(
            goal_id,
            "check_in",
            object_literal=f"{when}|{int(percent)}|{note}",
            valid_from=when,
        )
        return {"fact_id": fact_id, "at": when, "percent": int(percent), "note": note}

    def _facts_by_subject(self, subject: str) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for fact in self._graph.query_all_facts(entity=subject):
            if fact.get("subject") != subject:
                continue
            out.setdefault(fact.get("predicate", ""), []).append(fact)
        return out

    def _first_literal(self, facts: dict[str, list[dict]], pred: str, default: str = "") -> str:
        rows = facts.get(pred) or []
        if not rows:
            return default
        return rows[-1].get("object_literal") or default

    def list_goals(self) -> list[dict]:
        goals: list[dict] = []
        for ent in self._graph.list_entities("goal"):
            gid = ent.get("entity_id", "")
            facts = self._facts_by_subject(gid)
            check_ins = []
            for f in facts.get("check_in", []):
                raw = f.get("object_literal") or ""
                parts = raw.split("|", 2)
                if len(parts) == 3:
                    check_ins.append(
                        {"at": parts[0], "percent": int(parts[1] or 0), "note": parts[2],
                         "fact_id": f.get("fact_id")}
                    )
            check_ins.sort(key=lambda c: c["at"])
            goals.append(
                {
                    "goal_id": gid,
                    "title": ent.get("label", gid),
                    "category": self._first_literal(facts, "category", "General"),
                    "description": self._first_literal(facts, "description"),
                    "status": self._first_literal(facts, "status", "in_progress"),
                    "target_date": self._first_literal(facts, "target_date") or None,
                    "check_ins": check_ins,
                    "progress": check_ins[-1]["percent"] if check_ins else 0,
                }
            )
        goals.sort(key=lambda g: g["target_date"] or "9999")
        return goals

    # ── Life timeline (extensions §1 "life dashboard") ───────────────

    def add_event(
        self,
        title: str,
        *,
        event_date: str | None = None,
        category: str = "General",
        description: str = "",
        document_id: str | None = None,
    ) -> str:
        if not title.strip():
            raise ValueError("title is required")
        self.ensure_user()
        eid = f"event_{_slug(title)}_{_short_hash(title)}"
        self._graph.add_entity(eid, title.strip(), "timeline_event")
        if event_date:
            self._set_literal(eid, "event_date", event_date)
        self._set_literal(eid, "event_category", category)
        if description:
            self._set_literal(eid, "description", description)
        if document_id and self._graph.has_entity(document_id):
            self._set_link(eid, "references_document", document_id)
        self._set_link(USER_ID, "milestone", eid)
        return eid

    def list_events(self) -> list[dict]:
        events: list[dict] = []
        for ent in self._graph.list_entities("timeline_event"):
            eid = ent.get("entity_id", "")
            facts = self._facts_by_subject(eid)
            refs = facts.get("references_document", [])
            doc_ref = refs[-1].get("object") if refs else None
            events.append(
                {
                    "event_id": eid,
                    "title": ent.get("label", eid),
                    "event_date": self._first_literal(facts, "event_date") or None,
                    "category": self._first_literal(facts, "event_category", "General"),
                    "description": self._first_literal(facts, "description"),
                    "document_id": doc_ref,
                }
            )
        events.sort(key=lambda e: e["event_date"] or "9999-99-99")
        return events

    def counts(self) -> dict:
        people = [
            e for e in self._graph.list_entities("person")
            if e.get("entity_id") != USER_ID
        ]
        return {
            "fields": len(self.get_profile()),
            "people": len(people),
            "goals": len(self.list_goals()),
            "events": len(self.list_events()),
        }
