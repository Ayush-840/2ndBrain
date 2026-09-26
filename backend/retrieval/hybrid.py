"""Hybrid retrieval: fuses dense, BM25, and graph search.

Uses Reciprocal Rank Fusion (RRF) to combine three ranked lists:
  1. Dense (ChromaDB vector similarity) — semantic matching
  2. BM25 (lexical keyword matching) — exact term matching
  3. Graph (entity traversal) — structured relationship matching

The graph source is what makes this system fundamentally different from
plain RAG: it can answer questions that require following entity
relationships, not just finding similar text.

Phase 7 adds a fourth, non-fused source: when a query asks *which file do I
need* rather than *what does this say*, Document nodes are boosted ahead of
the fused list based on their purpose_tags / usage_context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.config import settings
from backend.enrichment.embedder import embed_query
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.retrieval.bm25 import BM25Index
from backend.retrieval.graph_retrieval import GraphRetriever

# "which document do I need for the tax filing", "that PDF I sent myself",
# "what file for my visa renewal" — queries about *purpose*, not content.
_DOC_INTENT = re.compile(
    r"\b(which|what|where|find|send me|do i have)\b[^?]{0,60}?"
    r"\b(document|file|pdf|form|attachment|paper|copy|scan)\b"
    r"|\bdo i need\b[^?]{0,40}?\bfor\b"
    r"|\b(which|what)\b[^?]{0,40}?\b(form|document|file)\b[^?]{0,40}?\bfor\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "which", "what", "where", "is", "of", "for", "do",
    "i", "need", "my", "me", "that", "this", "in", "on", "to", "and",
    "was", "were", "it", "have", "has", "find", "send", "file", "files",
    "document", "documents", "pdf", "attachment", "paper", "copy", "scan",
}


def _query_tokens(query: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", query.lower())
        if t not in _STOPWORDS and len(t) > 2
    }


@dataclass
class SearchResult:
    id: str
    text: str
    score: float
    source: str  # "dense", "bm25", "graph", or combination
    metadata: dict


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    weights: list[float],
    k: int = 60,
) -> list[dict]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = sum_i( weight_i / (k + rank_i) ) for each result across lists.

    Args:
        ranked_lists: List of ranked result lists. Each item must have "id".
        weights: Weight for each ranked list (same length as ranked_lists).
        k: Constant that controls how much lower-ranked items are penalized.

    Returns:
        Merged list sorted by combined RRF score, descending.
    """
    scores: dict[str, float] = {}
    id_to_item: dict[str, dict] = {}

    for ranked, weight in zip(ranked_lists, weights):
        for rank, item in enumerate(ranked):
            doc_id = item["id"]
            rrf = weight / (k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0.0) + rrf
            # Prefer the entry with more metadata
            if doc_id not in id_to_item or len(item.get("metadata", {})) > len(
                id_to_item[doc_id].get("metadata", {})
            ):
                id_to_item[doc_id] = item

    ranked_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results: list[dict] = []
    for doc_id, score in ranked_results:
        item = id_to_item[doc_id]
        results.append(
            {
                "id": doc_id,
                "text": item["text"],
                "score": score,
                "metadata": item.get("metadata", {}),
            }
        )
    return results


class HybridRetriever:
    """Fuses dense, BM25, and graph search.

    This is the core retrieval engine of the second brain.  It combines:
      - Episodic memory (what was written) via dense + BM25
      - Semantic memory (what's known) via graph traversal
    """

    def __init__(
        self,
        episodic_store: EpisodicStore,
        bm25_index: BM25Index | None = None,
        graph: TemporalGraph | None = None,
    ):
        self._store = episodic_store
        self._bm25 = bm25_index or BM25Index()
        self._graph = graph
        self._graph_retriever = GraphRetriever(graph) if graph else None

    @property
    def bm25(self) -> BM25Index:
        return self._bm25

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        dense_weight: float | None = None,
        bm25_weight: float | None = None,
        graph_weight: float | None = None,
        graph_hops: int | None = None,
        valid_as_of: str | None = None,
        boost_documents: bool = True,
    ) -> list[SearchResult]:
        """Run hybrid search and return fused, ranked results.

        Combines three sources:
          1. Dense (ChromaDB) — finds semantically similar text chunks
          2. BM25 — finds keyword-matching text chunks
          3. Graph — finds facts connected to entities mentioned in the query

        Args:
            query: Natural language query.
            top_k: Number of final results to return.
            dense_weight: Weight for dense (vector) results.
            bm25_weight: Weight for BM25 (lexical) results.
            graph_weight: Weight for graph traversal results.
            graph_hops: How many hops to traverse in the graph.
            valid_as_of: If set, only return graph facts valid at this date.
            boost_documents: Rank purpose-matched Document nodes first when the
                query is about *which file*, not *what does it say*.
        """
        top_k = top_k or settings.top_k
        dense_w = dense_weight if dense_weight is not None else settings.dense_weight
        bm25_w = bm25_weight if bm25_weight is not None else settings.bm25_weight
        graph_w = graph_weight if graph_weight is not None else settings.graph_weight
        hops = graph_hops if graph_hops is not None else settings.graph_hops

        # ── Source 1: Dense search via ChromaDB ──
        query_emb = embed_query(query)
        dense_results = self._store.query(query_emb, top_k=top_k)
        dense_ranked = [
            {
                "id": r["id"],
                "text": r["text"],
                "metadata": r["metadata"],
            }
            for r in dense_results
        ]

        # ── Source 2: BM25 lexical search ──
        bm25_results = self._bm25.search(query, top_k=top_k)

        # ── Source 3: Graph traversal ──
        graph_ranked: list[dict] = []
        graph_ids: set[str] = set()
        if self._graph_retriever:
            graph_results = self._graph_retriever.search(
                query,
                top_k=top_k,
                hops=hops,
                valid_as_of=valid_as_of,
            )
            graph_ranked = [
                {
                    "id": r.fact_id,
                    "text": r.text,
                    "metadata": r.metadata,
                }
                for r in graph_results
            ]
            graph_ids = {r.fact_id for r in graph_results}

        # ── Fuse all three with RRF ──
        ranked_lists = [dense_ranked, bm25_results, graph_ranked]
        weights = [dense_w, bm25_w, graph_w]

        # ── Purpose-aware document boost (computed even if no other sources) ──
        boosted: list[SearchResult] = []
        if boost_documents:
            boosted = self._purpose_boost(query)

        # Only include non-empty lists
        active_lists = [(lst, w) for lst, w in zip(ranked_lists, weights) if lst]
        if not active_lists:
            return boosted

        merged = reciprocal_rank_fusion(
            ranked_lists=[lst for lst, _ in active_lists],
            weights=[w for _, w in active_lists],
        )

        # Determine source attribution for each result
        dense_ids = {r["id"] for r in dense_ranked}
        bm25_ids = {r["id"] for r in bm25_results}

        output: list[SearchResult] = []
        for item in merged[:top_k]:
            doc_id = item["id"]
            in_dense = doc_id in dense_ids
            in_bm25 = doc_id in bm25_ids
            in_graph = doc_id in graph_ids

            # Build source tag
            sources = []
            if in_dense:
                sources.append("dense")
            if in_bm25:
                sources.append("bm25")
            if in_graph:
                sources.append("graph")
            source = "+".join(sources) if sources else "unknown"

            output.append(
                SearchResult(
                    id=doc_id,
                    text=item["text"],
                    score=item["score"],
                    source=source,
                    metadata=item["metadata"],
                )
            )

        if boosted:
            seen = {r.id for r in boosted}
            output = boosted + [r for r in output if r.id not in seen]
            output = output[: max(top_k, len(boosted))]

        return output

    def _purpose_boost(self, query: str, max_docs: int = 3) -> list[SearchResult]:
        """Purpose-aware boost: rank Document nodes by how well they match intent.

        Semantic search over raw text answers "what is this about"; this answers
        "which file do I need for X" — the question documents were stored *for*.
        Returns [] unless the query is document-shaped and documents exist.
        """
        if self._graph is None or not _DOC_INTENT.search(query):
            return []

        docs = self._graph.list_documents()
        tokens = _query_tokens(query)
        if not docs or not tokens:
            return []

        scored: list[tuple[float, dict]] = []
        for doc in docs:
            tags = {t.lower() for t in doc.get("purpose_tags", [])}
            haystack = " ".join(
                filter(
                    None,
                    [
                        doc.get("title") or "",
                        doc.get("usage_context") or "",
                        doc.get("filename") or "",
                        " ".join(tags),
                    ],
                )
            ).lower()
            overlap = tokens & set(re.findall(r"[a-z0-9]+", haystack))
            tag_hits = {t for t in tags if any(tok in t or t in tok for tok in tokens)}
            if not overlap and not tag_hits:
                continue

            score = len(overlap) + 2.0 * len(tag_hits)
            days_left = doc.get("days_left")
            if days_left is not None and days_left <= 0:
                score += 0.5  # stale-but-urgent documents surface first
            scored.append((score, doc))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        results: list[SearchResult] = []
        for score, doc in scored[:max_docs]:
            chunks = self._store.get_by_capture(doc.get("episodic_ref", ""), limit=1)
            purpose_line = f"{doc.get('title') or 'document'} — {doc.get('usage_context') or 'no purpose recorded'}"
            body = chunks[0]["text"] if chunks else ""
            text = f"{purpose_line}\n\n{body[:800]}" if body else purpose_line

            results.append(
                SearchResult(
                    id=chunks[0]["id"] if chunks else doc.get("document_id", ""),
                    text=text,
                    score=round(1.0 + score / 10.0, 4),  # outranks RRF scores (≤1)
                    source="document+purpose",
                    metadata={
                        "document_id": doc.get("document_id"),
                        "title": doc.get("title"),
                        "usage_context": doc.get("usage_context"),
                        "purpose_tags": doc.get("purpose_tags", []),
                        "source_channel": doc.get("source_channel"),
                        "valid_until": doc.get("valid_until"),
                    },
                )
            )
        return results
