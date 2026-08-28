"""Graph-aware retrieval layer.

Given a natural language query:
  1. Extract entity mentions by matching against known graph entities
  2. Traverse the graph from those entities (N-hop neighbors)
  3. Return connected facts as ranked results

This produces a third ranked list that fuses with dense + BM25 via RRF,
enabling answers that pull both similar text AND graph-connected facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.memory.graph import TemporalGraph


def _normalize(text: str) -> str:
    """Lowercase and strip for matching."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _extract_entity_mentions(
    query: str,
    entities: list[dict],
) -> list[dict]:
    """Match query text against known entity labels and IDs.

    Uses a simple substring matching approach — fast and sufficient for v1.
    Could be upgraded to NER or LLM-based entity linking later.

    Returns matched entities sorted by match quality (longest match first).
    """
    query_lower = _normalize(query)
    query_tokens = set(query_lower.split())

    matches: list[dict] = []
    for ent in entities:
        label = ent.get("label", "")
        eid = ent.get("entity_id", "")
        label_norm = _normalize(label)
        eid_norm = _normalize(eid)

        # Check if the label or ID appears in the query
        score = 0.0
        if label_norm in query_lower:
            # Longer label matches are more specific → higher score
            score = len(label_norm) / max(len(query_lower), 1)
        elif eid_norm in query_lower:
            score = len(eid_norm) / max(len(query_lower), 1)
        else:
            # Token overlap: how many query tokens appear in the entity label
            label_tokens = set(label_norm.split())
            overlap = query_tokens & label_tokens
            if len(overlap) >= 2:  # require at least 2 tokens
                score = len(overlap) / max(len(label_tokens), 1) * 0.5

        if score > 0:
            matches.append({**ent, "_match_score": score})

    # Sort by match score descending
    matches.sort(key=lambda x: x["_match_score"], reverse=True)
    return matches


@dataclass
class GraphResult:
    fact_id: str
    subject: str
    predicate: str
    object: str
    object_literal: str | None
    text: str  # human-readable representation of the fact
    score: float
    metadata: dict


class GraphRetriever:
    """Retrieves facts from the knowledge graph based on query entities."""

    def __init__(self, graph: TemporalGraph):
        self._graph = graph

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        hops: int = 2,
        valid_as_of: str | None = None,
    ) -> list[GraphResult]:
        """Search the graph for facts related to the query.

        Steps:
          1. Match query against known entities
          2. Traverse N-hop neighbors from matched entities
          3. Rank and return top-k facts

        Args:
            query: Natural language query.
            top_k: Maximum results to return.
            hops: Number of graph hops to traverse.
            valid_as_of: If set, only traverse valid facts at this time.
        """
        # 1. Find entity mentions in the query
        all_entities = self._graph.list_entities()
        matched = _extract_entity_mentions(query, all_entities)

        if not matched:
            return []

        # 2. Traverse from each matched entity
        seen_facts: set[str] = set()
        results: list[GraphResult] = []

        for ent in matched[:5]:  # limit to top 5 matches
            entity_id = ent["entity_id"]
            match_score = ent["_match_score"]

            neighbors = self._graph.neighbors(
                entity_id,
                hops=hops,
                valid_as_of=valid_as_of,
            )

            for fact in neighbors:
                fact_id = fact.get("fact_id", "")
                if fact_id in seen_facts:
                    continue
                seen_facts.add(fact_id)

                # Build human-readable text from the fact
                text = self._fact_to_text(fact)

                # Score: combine match quality with graph proximity
                # Facts directly connected to the entity get a boost
                subject = fact.get("subject", "")
                direct = subject == entity_id
                proximity = 1.0 if direct else 0.5

                score = match_score * proximity

                results.append(
                    GraphResult(
                        fact_id=fact_id,
                        subject=subject,
                        predicate=fact.get("predicate", ""),
                        object=fact.get("object", ""),
                        object_literal=fact.get("object_literal"),
                        text=text,
                        score=score,
                        metadata={
                            "valid_from": fact.get("valid_from"),
                            "valid_to": fact.get("valid_to"),
                            "recorded_at": fact.get("recorded_at"),
                            "confidence": fact.get("confidence", 1.0),
                            "matched_entity": entity_id,
                            "direct_connection": direct,
                        },
                    )
                )

        # Sort by score and return top-k
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _fact_to_text(self, fact: dict) -> str:
        """Convert a graph fact to human-readable text."""
        subject = fact.get("subject", "")
        predicate = fact.get("predicate", "")
        obj = fact.get("object_literal") or fact.get("object", "")

        # Get entity labels if available
        subj_entity = self._graph.get_entity(subject)
        if subj_entity:
            subject = subj_entity["label"]

        if obj.startswith("_literal:"):
            obj = obj[len("_literal:"):]
        else:
            obj_entity = self._graph.get_entity(obj)
            if obj_entity:
                obj = obj_entity["label"]

        # Format: "Subject predicate Object"
        predicate_readable = predicate.replace("_", " ")
        text = f"{subject} {predicate_readable} {obj}"

        # Add temporal context
        vf = fact.get("valid_from")
        vt = fact.get("valid_to")
        if vf:
            if vt:
                text += f" (from {vf} to {vt})"
            else:
                text += f" (since {vf})"

        return text
