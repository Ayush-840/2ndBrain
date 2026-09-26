"""Bi-temporal knowledge graph — NetworkX implementation.

The semantic tier of the memory system.  Every fact carries two timelines:
  - valid_from / valid_to: when the fact was true in the world
  - recorded_at: when the system learned it

This split makes point-in-time queries possible and lets new facts
supersede old ones without deleting history.

Schema
------
Nodes (entities):
    entity_id   : str   — unique identifier (lowercase slug)
    label       : str   — human-readable name
    entity_type : str   — "person", "concept", "tool", "paper", etc.

Edges (facts):
    fact_id            : str   — unique ID
    predicate          : str   — relationship label (e.g. "works_on", "believes")
    source_episode_id  : str   — which capture/chunk produced this fact
    valid_from         : str|None — ISO8601, when fact became true in the world
    valid_to           : str|None — ISO8601, when fact stopped being true
    recorded_at        : str   — ISO8601, when system learned it
    confidence         : float — 0..1
    superseded_by      : str|None — fact_id of the fact that replaced this one
    object_literal     : str|None — for facts with a literal object (not an entity)

Document nodes (Phase 6 — "files with a purpose"):
    entity_type == "document" distinguishes them from normal entities.
    They reuse the same bi-temporal fields as facts: a corrected
    usage_context closes the old node (valid_to + superseded_by) and
    links to a new one — history is refined, never overwritten.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path
from uuid import uuid4

import networkx as nx


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse an ISO8601 date or datetime string."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _dates_overlap(
    a_from: str | None, a_to: str | None,
    b_from: str | None, b_to: str | None,
) -> bool:
    """Check if two validity windows overlap.

    A window with None end is open-ended (still valid).
    Two windows overlap if each starts before the other ends.
    """
    a_start = _parse_date(a_from) or datetime.min.replace(tzinfo=timezone.utc)
    a_end = _parse_date(a_to) or datetime.max.replace(tzinfo=timezone.utc)
    b_start = _parse_date(b_from) or datetime.min.replace(tzinfo=timezone.utc)
    b_end = _parse_date(b_to) or datetime.max.replace(tzinfo=timezone.utc)
    return a_start <= b_end and b_start <= a_end


class TemporalGraph:
    """In-memory bi-temporal knowledge graph backed by NetworkX.

    Uses a MultiDiGraph so multiple facts can exist between the same
    entity pair (different predicates or time periods).
    """

    def __init__(self):
        self._graph = nx.MultiDiGraph()

    # ── Document operations (Phase 6) ────────────────────────────────

    def add_document(
        self,
        *,
        title: str,
        usage_context: str,
        purpose_tags: list[str] | None = None,
        source_channel: str = "unknown",
        episodic_ref: str = "",
        filename: str | None = None,
        mime_type: str | None = None,
        blob_path: str | None = None,
        source_message_id: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        valid_to: str | None = None,
        superseded_from: str | None = None,
        inferred_by: str = "heuristic",
        confidence: float = 1.0,
    ) -> str:
        """Create a Document node. Returns the new document id."""
        doc_id = f"doc_{uuid4().hex[:16]}"
        now = _now_iso()
        self._graph.add_node(
            doc_id,
            entity_id=doc_id,
            label=title,
            entity_type="document",
            document_id=doc_id,
            title=title,
            usage_context=usage_context,
            purpose_tags=list(purpose_tags or []),
            source_channel=source_channel,
            source_message_id=source_message_id,
            episodic_ref=episodic_ref,
            filename=filename,
            mime_type=mime_type,
            blob_path=blob_path,
            valid_from=valid_from or now,
            valid_to=valid_to,
            valid_until=valid_until,
            recorded_at=now,
            superseded_by=None,
            superseded_from=superseded_from,
            inferred_by=inferred_by,
            confidence=confidence,
        )
        return doc_id

    def get_document(self, doc_id: str) -> dict | None:
        """Return a document node, or None. Superseded docs are returned as-is."""
        if not self._graph.has_node(doc_id):
            return None
        data = dict(self._graph.nodes[doc_id])
        if data.get("entity_type") != "document":
            return None
        return data

    def list_documents(
        self,
        *,
        purpose_tag: str | None = None,
        include_superseded: bool = False,
    ) -> list[dict]:
        """List documents, newest first.

        Args:
            purpose_tag: Keep only documents carrying this tag (case-insensitive).
            include_superseded: Include closed (corrected) versions too.
        """
        docs: list[dict] = []
        for _, data in self._graph.nodes(data=True):
            if data.get("entity_type") != "document":
                continue
            if not include_superseded and data.get("superseded_by"):
                continue
            if purpose_tag:
                tags = [t.lower() for t in data.get("purpose_tags", [])]
                if purpose_tag.lower() not in tags:
                    continue
            docs.append(dict(data))
        docs.sort(key=lambda d: d.get("recorded_at") or "", reverse=True)
        return docs

    def correct_document(
        self,
        doc_id: str,
        *,
        usage_context: str,
        purpose_tags: list[str] | None = None,
        valid_until: str | None = None,
        title: str | None = None,
    ) -> dict | None:
        """Supersede a document's purpose — the bi-temporal way.

        The old node's validity window is closed (valid_to + superseded_by)
        and a new node carries the correction. Nothing is ever overwritten.
        Returns the new document, or None if doc_id isn't an open document.
        """
        old = self.get_document(doc_id)
        if old is None or old.get("superseded_by"):
            return None

        new_id = self.add_document(
            title=title or old.get("title", ""),
            usage_context=usage_context,
            purpose_tags=purpose_tags if purpose_tags is not None else old.get("purpose_tags", []),
            source_channel=old.get("source_channel", "unknown"),
            episodic_ref=old.get("episodic_ref", ""),
            filename=old.get("filename"),
            mime_type=old.get("mime_type"),
            blob_path=old.get("blob_path"),
            source_message_id=old.get("source_message_id"),
            valid_from=old.get("valid_from"),
            valid_until=valid_until if valid_until is not None else old.get("valid_until"),
            superseded_from=doc_id,
            inferred_by="user",
            confidence=1.0,
        )

        self._graph.nodes[doc_id]["valid_to"] = _now_iso()
        self._graph.nodes[doc_id]["superseded_by"] = new_id
        return self.get_document(new_id)

    def documents_expiring(
        self,
        within_days: int = 30,
        *,
        now: datetime | None = None,
    ) -> list[dict]:
        """Documents whose valid_until falls within N days (or already passed).

        Each result carries ``days_left`` (negative = already expired) and a
        ``status`` of "red" (≤ 0 days... within a quarter of the window),
        "amber" (approaching), or "green".
        """
        ref = now or datetime.now(UTC)
        results: list[dict] = []
        for doc in self.list_documents():
            until = _parse_date(doc.get("valid_until"))
            if until is None:
                continue
            days_left = (until - ref).days
            if days_left > within_days:
                status = "green"
            elif days_left > max(1, within_days // 3):
                status = "amber"
            else:
                status = "red"
            entry = dict(doc)
            entry["days_left"] = days_left
            entry["status"] = status
            results.append(entry)
        results.sort(key=lambda d: d["days_left"])
        return results

    @property
    def document_count(self) -> int:
        return sum(
            1 for _, d in self._graph.nodes(data=True) if d.get("entity_type") == "document"
        )

    # ── Entity operations ────────────────────────────────────────────

    def add_entity(
        self,
        entity_id: str,
        label: str,
        entity_type: str = "concept",
    ) -> str:
        """Add or update an entity node.  Returns the entity_id."""
        eid = entity_id.lower().strip().replace(" ", "_")
        if self._graph.has_node(eid):
            # Update label/type if provided
            self._graph.nodes[eid]["label"] = label
            self._graph.nodes[eid]["entity_type"] = entity_type
        else:
            self._graph.add_node(
                eid,
                entity_id=eid,
                label=label,
                entity_type=entity_type,
            )
        return eid

    def get_entity(self, entity_id: str) -> dict | None:
        """Return entity node data, or None if not found."""
        if self._graph.has_node(entity_id):
            return dict(self._graph.nodes[entity_id])
        return None

    def has_entity(self, entity_id: str) -> bool:
        return self._graph.has_node(entity_id)

    def list_entities(self, entity_type: str | None = None) -> list[dict]:
        """List all entities, optionally filtered by type."""
        entities = []
        for nid, data in self._graph.nodes(data=True):
            if entity_type and data.get("entity_type") != entity_type:
                continue
            entities.append(dict(data))
        return entities

    # ── Fact operations ──────────────────────────────────────────────

    def add_fact(
        self,
        subject_id: str,
        predicate: str,
        *,
        object_id: str | None = None,
        object_literal: str | None = None,
        source_episode_id: str = "",
        valid_from: str | None = None,
        valid_to: str | None = None,
        recorded_at: str | None = None,
        confidence: float = 1.0,
    ) -> str:
        """Add a fact edge to the graph.  Returns the fact_id.

        A fact connects subject → object (entity or literal) via a predicate.
        Exactly one of object_id or object_literal must be provided.
        """
        if (object_id is None) == (object_literal is None):
            raise ValueError("Provide exactly one of object_id or object_literal")

        fact_id = uuid4().hex
        now = recorded_at or _now_iso()

        edge_data = {
            "fact_id": fact_id,
            "predicate": predicate,
            "source_episode_id": source_episode_id,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "recorded_at": now,
            "confidence": confidence,
            "superseded_by": None,
            "object_literal": object_literal,
        }

        if object_id:
            self._graph.add_edge(subject_id, object_id, **edge_data)
        else:
            # Literal objects: use a special sink node
            lit_node = f"_literal:{object_literal}"
            self._graph.add_node(lit_node, entity_type="literal", label=object_literal)
            self._graph.add_edge(subject_id, lit_node, **edge_data)

        return fact_id

    def get_fact(self, fact_id: str) -> dict | None:
        """Look up a fact by its ID."""
        for u, v, data in self._graph.edges(data=True):
            if data.get("fact_id") == fact_id:
                edge = dict(data)
                edge["subject"] = u
                edge["object"] = v
                return edge
        return None

    def _set_fact_superseded(self, fact_id: str, superseded_by: str) -> None:
        """Mark a fact as superseded and close its validity window."""
        for u, v, key, data in self._graph.edges(data=True, keys=True):
            if data.get("fact_id") == fact_id:
                self._graph.edges[u, v, key]["superseded_by"] = superseded_by
                # Close the validity window if still open
                if data.get("valid_to") is None:
                    self._graph.edges[u, v, key]["valid_to"] = _now_iso()
                break

    # ── Point-in-time queries ────────────────────────────────────────

    def query_as_of(
        self,
        date: str,
        *,
        entity: str | None = None,
        predicate: str | None = None,
    ) -> list[dict]:
        """Return facts valid as of a given date.

        A fact is "valid as of date" if:
          - valid_from <= date (or valid_from is None)
          - valid_to >= date (or valid_to is None, meaning still active)

        Superseded facts ARE included if the query date is before the
        supersession — i.e. the fact was still the active belief at that
        point in time.

        Args:
            date: ISO8601 date or datetime string.
            entity: Optional entity_id to filter by (subject or object).
            predicate: Optional predicate to filter by.
        """
        query_dt = _parse_date(date)
        if query_dt is None:
            raise ValueError(f"Cannot parse date: {date}")

        # Ensure timezone-aware
        if query_dt.tzinfo is None:
            query_dt = query_dt.replace(tzinfo=timezone.utc)

        results: list[dict] = []
        for u, v, data in self._graph.edges(data=True):
            # Check validity window
            vf = _parse_date(data.get("valid_from"))
            vt = _parse_date(data.get("valid_to"))

            # fact starts before or at query date
            if vf and vf > query_dt:
                continue
            # fact ends before query date
            if vt and vt < query_dt:
                continue

            # For superseded facts: only include if the supersession
            # happened AFTER the query date (fact was still active then)
            if data.get("superseded_by"):
                superseding_fact = self.get_fact(data["superseded_by"])
                if superseding_fact:
                    sup_recorded = _parse_date(superseding_fact.get("recorded_at"))
                    if sup_recorded and sup_recorded <= query_dt:
                        continue  # already superseded by query date

            # Optional filters
            if predicate and data.get("predicate") != predicate:
                continue
            if entity and u != entity and v != entity:
                continue

            fact = dict(data)
            fact["subject"] = u
            fact["object"] = v
            results.append(fact)

        return results

    def query_all_facts(
        self,
        *,
        include_superseded: bool = False,
        entity: str | None = None,
    ) -> list[dict]:
        """Return all facts, optionally including superseded ones."""
        results: list[dict] = []
        for u, v, data in self._graph.edges(data=True):
            if not include_superseded and data.get("superseded_by"):
                continue
            if entity and u != entity and v != entity:
                continue
            fact = dict(data)
            fact["subject"] = u
            fact["object"] = v
            results.append(fact)
        return results

    # ── Contradiction detection ──────────────────────────────────────

    def find_contradictions(
        self,
        subject_id: str,
        predicate: str,
        object_value: str,
        *,
        valid_from: str | None = None,
        valid_to: str | None = None,
    ) -> list[dict]:
        """Find existing facts that contradict a proposed new fact.

        Two facts contradict if they share the same subject + predicate
        but have different objects, AND their validity windows overlap.

        Returns a list of existing fact dicts that conflict.
        """
        contradictions: list[dict] = []

        for u, v, data in self._graph.edges(data=True):
            if data.get("superseded_by"):
                continue  # already superseded
            if u != subject_id or data.get("predicate") != predicate:
                continue

            # Get the object value to compare
            existing_object = data.get("object_literal") or v

            # Same object → not a contradiction
            if existing_object == object_value:
                continue

            # Check temporal overlap
            if _dates_overlap(
                valid_from, valid_to,
                data.get("valid_from"), data.get("valid_to"),
            ):
                contradictions.append(dict(data))
                contradictions[-1]["subject"] = u
                contradictions[-1]["object"] = v

        return contradictions

    def supersede_fact(
        self,
        old_fact_id: str,
        new_fact_id: str,
    ) -> bool:
        """Mark an old fact as superseded by a new one.

        Returns True if the old fact was found and updated.
        """
        old_fact = self.get_fact(old_fact_id)
        if not old_fact:
            return False
        self._set_fact_superseded(old_fact_id, new_fact_id)
        return True

    def supersede_and_add(
        self,
        subject_id: str,
        predicate: str,
        *,
        object_id: str | None = None,
        object_literal: str | None = None,
        source_episode_id: str = "",
        valid_from: str | None = None,
        valid_to: str | None = None,
        confidence: float = 1.0,
    ) -> dict:
        """Add a new fact and automatically supersede any contradicting facts.

        Returns a dict with:
          - new_fact_id: the ID of the newly added fact
          - superseded: list of fact IDs that were superseded
        """
        # Find contradictions first
        obj_val = object_literal or object_id or ""
        contradictions = self.find_contradictions(
            subject_id, predicate, obj_val,
            valid_from=valid_from, valid_to=valid_to,
        )

        # Add the new fact
        new_fact_id = self.add_fact(
            subject_id,
            predicate,
            object_id=object_id,
            object_literal=object_literal,
            source_episode_id=source_episode_id,
            valid_from=valid_from,
            valid_to=valid_to,
            confidence=confidence,
        )

        # Supersede old facts
        superseded_ids: list[str] = []
        for old_fact in contradictions:
            old_id = old_fact["fact_id"]
            self._set_fact_superseded(old_id, new_fact_id)
            superseded_ids.append(old_id)

        return {
            "new_fact_id": new_fact_id,
            "superseded": superseded_ids,
        }

    # ── Graph traversal ──────────────────────────────────────────────

    def neighbors(
        self,
        entity_id: str,
        *,
        hops: int = 1,
        valid_as_of: str | None = None,
    ) -> list[dict]:
        """Return facts within N hops of an entity.

        If valid_as_of is provided, only traverses valid facts at that time.
        """
        visited: set[str] = set()
        results: list[dict] = []
        frontier = {entity_id}

        for _ in range(hops):
            next_frontier: set[str] = set()
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)

                for u, v, data in self._graph.edges(node, data=True):
                    # Time filter
                    if valid_as_of:
                        vf = _parse_date(data.get("valid_from"))
                        vt = _parse_date(data.get("valid_to"))
                        query_dt = _parse_date(valid_as_of)
                        if query_dt and vf and vf > query_dt:
                            continue
                        if query_dt and vt and vt < query_dt:
                            continue

                    if data.get("superseded_by"):
                        continue

                    fact = dict(data)
                    fact["subject"] = u
                    fact["object"] = v
                    results.append(fact)
                    next_frontier.add(v)

                # Also check incoming edges
                for v, u, data in self._graph.in_edges(node, data=True):
                    if valid_as_of:
                        vf = _parse_date(data.get("valid_from"))
                        vt = _parse_date(data.get("valid_to"))
                        query_dt = _parse_date(valid_as_of)
                        if query_dt and vf and vf > query_dt:
                            continue
                        if query_dt and vt and vt < query_dt:
                            continue

                    if data.get("superseded_by"):
                        continue

                    fact = dict(data)
                    fact["subject"] = v
                    fact["object"] = u
                    results.append(fact)
                    next_frontier.add(v)

            frontier = next_frontier - visited

        return results

    # ── Stats & serialization ────────────────────────────────────────

    @property
    def entity_count(self) -> int:
        # Exclude literal sinks and document nodes (both are payload, not entities)
        return sum(
            1 for _, d in self._graph.nodes(data=True)
            if d.get("entity_type") not in ("literal", "document")
        )

    @property
    def fact_count(self) -> int:
        return self._graph.number_of_edges()

    @property
    def active_fact_count(self) -> int:
        return len(self.query_all_facts(include_superseded=False))

    def stats(self) -> dict:
        return {
            "entities": self.entity_count,
            "facts": self.fact_count,
            "active_facts": self.active_fact_count,
            "total_nodes": self._graph.number_of_nodes(),
        }

    def save(self, path: str) -> None:
        """Serialize the graph to JSON."""
        data = nx.node_link_data(self._graph)
        Path(path).write_text(json.dumps(data, indent=2, default=str))

    def load(self, path: str) -> None:
        """Load the graph from a JSON file."""
        data = json.loads(Path(path).read_text())
        self._graph = nx.node_link_graph(data)
