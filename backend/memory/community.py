"""Community memory tier: topic clustering + LLM summarization.

The third tier of the three-tier memory system.  Takes facts from the
semantic graph, clusters them by topic (embedding similarity), and
produces LLM-generated summaries for each cluster.

This enables:
  - Topic-level queries ("what do I know about X?")
  - Cross-cutting synthesis ("how do my tools relate to each other?")
  - Digest generation (summarize recent activity by topic)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import networkx as nx
import numpy as np

from backend.config import settings
from backend.enrichment.embedder import embed_texts, embed_query
from backend.memory.graph import TemporalGraph

logger = logging.getLogger(__name__)


@dataclass
class TopicCluster:
    """A cluster of related facts with an LLM-generated summary."""

    cluster_id: str
    label: str  # auto-generated topic label
    summary: str  # LLM-generated summary
    fact_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    centroid_embedding: list[float] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


class CommunityStore:
    """In-memory community memory store backed by NetworkX.

    Stores topic clusters as nodes and assigns facts to clusters.
    Provides topic-level retrieval and digest generation.
    """

    def __init__(self):
        self._graph = nx.Graph()
        self._clusters: dict[str, TopicCluster] = {}
        self._fact_to_cluster: dict[str, str] = {}  # fact_id → cluster_id

    @property
    def cluster_count(self) -> int:
        return len(self._clusters)

    @property
    def total_facts_in_clusters(self) -> int:
        return sum(len(c.fact_ids) for c in self._clusters.values())

    def add_cluster(self, cluster: TopicCluster) -> str:
        """Add or update a topic cluster."""
        self._clusters[cluster.cluster_id] = cluster
        self._graph.add_node(
            cluster.cluster_id,
            label=cluster.label,
            summary=cluster.summary,
            fact_count=len(cluster.fact_ids),
            entity_count=len(cluster.entity_ids),
        )
        # Update fact-to-cluster mapping
        for fid in cluster.fact_ids:
            self._fact_to_cluster[fid] = cluster.cluster_id
        return cluster.cluster_id

    def get_cluster(self, cluster_id: str) -> TopicCluster | None:
        return self._clusters.get(cluster_id)

    def get_cluster_for_fact(self, fact_id: str) -> TopicCluster | None:
        cid = self._fact_to_cluster.get(fact_id)
        if cid:
            return self._clusters.get(cid)
        return None

    def list_clusters(self) -> list[TopicCluster]:
        return list(self._clusters.values())

    def remove_cluster(self, cluster_id: str) -> bool:
        if cluster_id not in self._clusters:
            return False
        cluster = self._clusters[cluster_id]
        for fid in cluster.fact_ids:
            self._fact_to_cluster.pop(fid, None)
        del self._clusters[cluster_id]
        self._graph.remove_node(cluster_id)
        return True

    def search_clusters(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[TopicCluster, float]]:
        """Find clusters most relevant to a query by embedding similarity.

        Returns list of (cluster, score) tuples sorted by relevance.
        """
        if not self._clusters:
            return []

        query_emb = np.array(embed_query(query))

        scored: list[tuple[TopicCluster, float]] = []
        for cluster in self._clusters.values():
            if not cluster.centroid_embedding:
                continue
            cluster_emb = np.array(cluster.centroid_embedding)
            # Cosine similarity (embeddings are normalized)
            similarity = float(np.dot(query_emb, cluster_emb))
            scored.append((cluster, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def stats(self) -> dict:
        return {
            "clusters": self.cluster_count,
            "facts_in_clusters": self.total_facts_in_clusters,
            "avg_facts_per_cluster": (
                self.total_facts_in_clusters / self.cluster_count
                if self.cluster_count > 0
                else 0
            ),
        }

    def save(self, path: str) -> None:
        """Serialize to JSON."""
        data = {
            "clusters": {
                cid: {
                    "cluster_id": c.cluster_id,
                    "label": c.label,
                    "summary": c.summary,
                    "fact_ids": c.fact_ids,
                    "entity_ids": c.entity_ids,
                    "centroid_embedding": c.centroid_embedding,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                }
                for cid, c in self._clusters.items()
            },
            "fact_to_cluster": self._fact_to_cluster,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2, default=str))

    def load(self, path: str) -> None:
        """Load from JSON."""
        data = json.loads(Path(path).read_text())
        self._clusters.clear()
        self._fact_to_cluster.clear()
        self._graph.clear()

        for cid, cdata in data.get("clusters", {}).items():
            cluster = TopicCluster(**cdata)
            self.add_cluster(cluster)

        self._fact_to_cluster.update(data.get("fact_to_cluster", {}))


def cluster_facts(
    graph: TemporalGraph,
    max_clusters: int = 10,
    min_cluster_size: int = 2,
) -> list[TopicCluster]:
    """Cluster facts from the semantic graph by embedding similarity.

    Uses a simple approach:
    1. Embed each fact's text representation
    2. Use agglomerative clustering (scipy) or simple K-means
    3. Compute cluster centroids

    For v1, uses a simple greedy clustering approach that doesn't
    require scipy/sklearn dependencies.
    """
    facts = graph.query_all_facts(include_superseded=False)
    if not facts:
        return []

    # Build text representations for embedding
    fact_texts = []
    fact_ids = []
    for fact in facts:
        fid = fact.get("fact_id", "")
        text = _fact_to_graph_text(fact, graph)
        fact_texts.append(text)
        fact_ids.append(fid)

    # Embed all facts
    embeddings = embed_texts(fact_texts)
    embeddings_np = np.array(embeddings)

    # Simple greedy clustering based on cosine similarity threshold
    threshold = 0.5  # facts with similarity > threshold go in same cluster
    clusters: list[list[int]] = []  # indices of facts in each cluster
    cluster_centroids: list[np.ndarray] = []

    for i in range(len(fact_texts)):
        assigned = False
        for j, centroid in enumerate(cluster_centroids):
            sim = float(np.dot(embeddings_np[i], centroid))
            if sim > threshold:
                clusters[j].append(i)
                # Update centroid (running average)
                n = len(clusters[j])
                cluster_centroids[j] = (
                    centroid * (n - 1) + embeddings_np[i]
                ) / n
                assigned = True
                break

        if not assigned:
            clusters.append([i])
            cluster_centroids.append(embeddings_np[i].copy())

    # Filter out tiny clusters
    result_clusters: list[TopicCluster] = []
    for indices in clusters:
        if len(indices) < min_cluster_size:
            continue
        if len(result_clusters) >= max_clusters:
            break

        # Build cluster
        cluster_fids = [fact_ids[i] for i in indices]
        cluster_texts = [fact_texts[i] for i in indices]
        centroid = cluster_centroids[clusters.index(indices)]

        # Extract entities involved
        entity_ids = set()
        for i in indices:
            fact = facts[i]
            subj = fact.get("subject", "")
            obj = fact.get("object", "")
            if subj and not subj.startswith("_literal:"):
                entity_ids.add(subj)
            if obj and not obj.startswith("_literal:"):
                entity_ids.add(obj)

        # Generate a label from the most common entity/predicate
        label = _generate_cluster_label(facts, indices, graph)

        cluster = TopicCluster(
            cluster_id=uuid4().hex,
            label=label,
            summary="",  # will be filled by LLM
            fact_ids=cluster_fids,
            entity_ids=sorted(entity_ids),
            centroid_embedding=centroid.tolist(),
        )
        result_clusters.append(cluster)

    return result_clusters


def summarize_clusters(
    clusters: list[TopicCluster],
    graph: TemporalGraph,
    api_key: str | None = None,
) -> list[TopicCluster]:
    """Generate LLM summaries for each cluster.

    Uses Claude to produce a concise summary of the facts in each cluster.
    """
    import anthropic

    key = api_key or settings.anthropic_api_key
    if not key:
        # No API key — use simple extractive summaries
        for cluster in clusters:
            cluster.summary = _extractive_summary(cluster, graph)
        return clusters

    client = anthropic.Anthropic(api_key=key)
    model = settings.anthropic_model

    for cluster in clusters:
        # Build context from facts
        fact_texts = []
        for fid in cluster.fact_ids:
            fact = graph.get_fact(fid)
            if fact:
                text = _fact_to_graph_text(fact, graph)
                fact_texts.append(text)

        if not fact_texts:
            cluster.summary = "Empty cluster."
            continue

        facts_str = "\n".join(f"- {t}" for t in fact_texts)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Summarize these related facts into a concise 2-3 sentence "
                        f"topic summary. Focus on the key relationships and insights:\n\n"
                        f"{facts_str}"
                    ),
                }],
            )
            cluster.summary = response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"LLM summarization failed for cluster {cluster.cluster_id}: {e}")
            cluster.summary = _extractive_summary(cluster, graph)

    return clusters


def _extractive_summary(cluster: TopicCluster, graph: TemporalGraph) -> str:
    """Simple extractive summary when LLM is unavailable."""
    parts = []
    for fid in cluster.fact_ids[:5]:
        fact = graph.get_fact(fid)
        if fact:
            parts.append(_fact_to_graph_text(fact, graph))
    if not parts:
        return "No facts in this cluster."
    return f"Topic cluster ({len(cluster.fact_ids)} facts): " + "; ".join(parts[:3])


def _fact_to_graph_text(fact: dict, graph: TemporalGraph) -> str:
    """Convert a graph fact to readable text."""
    subject = fact.get("subject", "")
    predicate = fact.get("predicate", "").replace("_", " ")
    obj = fact.get("object_literal") or fact.get("object", "")

    # Resolve entity labels
    subj_entity = graph.get_entity(subject)
    if subj_entity:
        subject = subj_entity.get("label", subject)

    if obj.startswith("_literal:"):
        obj = obj[len("_literal:"):]
    else:
        obj_entity = graph.get_entity(obj)
        if obj_entity:
            obj = obj_entity.get("label", obj)

    text = f"{subject} {predicate} {obj}"

    vf = fact.get("valid_from")
    vt = fact.get("valid_to")
    if vf:
        text += f" (from {vf}"
        if vt:
            text += f" to {vt}"
        text += ")"

    return text


def _generate_cluster_label(
    facts: list[dict],
    indices: list[int],
    graph: TemporalGraph,
) -> str:
    """Generate a label for a cluster based on the most common entities/predicates."""
    from collections import Counter

    entity_counter = Counter()
    predicate_counter = Counter()

    for i in indices:
        fact = facts[i]
        subj = fact.get("subject", "")
        obj = fact.get("object", "")
        pred = fact.get("predicate", "")

        if subj and not subj.startswith("_literal:"):
            entity = graph.get_entity(subj)
            entity_counter[entity.get("label", subj) if entity else subj] += 1
        if obj and not obj.startswith("_literal:"):
            entity = graph.get_entity(obj)
            entity_counter[entity.get("label", obj) if entity else obj] += 1

        predicate_counter[pred.replace("_", " ")] += 1

    # Top entities + top predicate
    top_entities = [e for e, _ in entity_counter.most_common(2)]
    top_pred = predicate_counter.most_common(1)
    pred_str = top_pred[0][0] if top_pred else "related"

    if top_entities:
        return f"{', '.join(top_entities)} — {pred_str}"
    return f"Cluster ({len(indices)} facts)"
