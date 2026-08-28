"""End-to-end ingestion pipeline.

Phase 1: ingest → chunk → embed → store in ChromaDB + BM25
Phase 2: + extract entities/facts via Claude → store in bi-temporal graph

This is the main entry point the API routes call.
"""

from __future__ import annotations

import logging

from backend.config import settings
from backend.enrichment.chunker import Chunk, chunk_text
from backend.enrichment.embedder import embed_texts
from backend.enrichment.extractor import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedFact,
    FactExtractor,
)
from backend.ingestion.base import Capture, IngestionAdapter
from backend.ingestion.markdown import MarkdownAdapter
from backend.ingestion.pdf import PDFAdapter
from backend.ingestion.url_adapter import URLAdapter
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.memory.community import CommunityStore, cluster_facts, summarize_clusters
from backend.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)

# Adapter registry — maps source types to adapter classes
ADAPTERS: dict[str, type[IngestionAdapter]] = {
    "markdown": MarkdownAdapter,
    "pdf": PDFAdapter,
    "url": URLAdapter,
}


def get_adapter(source_type: str) -> IngestionAdapter:
    if source_type not in ADAPTERS:
        raise ValueError(f"Unknown source type: {source_type}. Available: {list(ADAPTERS)}")
    return ADAPTERS[source_type]()


class Pipeline:
    """Orchestrates ingestion → enrichment → storage (episodic + semantic)."""

    def __init__(
        self,
        episodic_store: EpisodicStore | None = None,
        bm25_index: BM25Index | None = None,
        graph: TemporalGraph | None = None,
        community: CommunityStore | None = None,
        extractor: FactExtractor | None = None,
    ):
        self.store = episodic_store or EpisodicStore()
        self.bm25 = bm25_index or BM25Index()
        self.graph = graph or TemporalGraph()
        self.community = community or CommunityStore()
        self._extractor = extractor  # lazy init — only when needed

    @property
    def extractor(self) -> FactExtractor:
        """Lazy-init the LLM extractor (only when API key is set)."""
        if self._extractor is None:
            if not settings.anthropic_api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Cannot run extraction. "
                    "Set BRAIN_ANTHROPIC_API_KEY in your environment."
                )
            self._extractor = FactExtractor()
        return self._extractor

    def ingest_source(
        self,
        source: str,
        source_type: str,
        *,
        extract: bool = False,
    ) -> dict:
        """Full pipeline: ingest → chunk → embed → store.

        Args:
            source: File path or directory path.
            source_type: "markdown" or "pdf".
            extract: If True, also run LLM extraction and populate the graph.

        Returns:
            Summary dict with counts and IDs.
        """
        adapter = get_adapter(source_type)
        captures = adapter.ingest(source)

        total_chunks = 0
        all_doc_ids: list[str] = []
        extraction_results: list[ExtractionResult] = []

        for capture in captures:
            result = self._process_capture(capture, extract=extract)
            total_chunks += result["num_chunks"]
            all_doc_ids.extend(result["doc_ids"])
            if result.get("extraction"):
                extraction_results.append(result["extraction"])

        summary: dict = {
            "num_captures": len(captures),
            "num_chunks": total_chunks,
            "doc_ids": all_doc_ids,
        }

        if extraction_results:
            total_entities = sum(len(r.entities) for r in extraction_results)
            total_facts = sum(len(r.facts) for r in extraction_results)
            summary["entities_extracted"] = total_entities
            summary["facts_extracted"] = total_facts

        return summary

    def ingest_capture(
        self,
        capture: Capture,
        *,
        extract: bool = False,
    ) -> dict:
        """Process a single pre-built Capture (e.g., from a URL endpoint)."""
        return self._process_capture(capture, extract=extract)

    def extract_and_store(
        self,
        text: str,
        *,
        source_episode_id: str = "",
        source_context: str = "",
    ) -> dict:
        """Run LLM extraction on a text and store results in the graph.

        Used for on-demand extraction from search results or specific chunks.
        """
        result = self.extractor.extract(text, source_context=source_context)

        entities_added = 0
        facts_added = 0
        contradictions_found = 0

        for ent in result.entities:
            self.graph.add_entity(ent.entity_id, ent.label, ent.entity_type)
            entities_added += 1

        for fact in result.facts:
            # Use supersede_and_add to handle contradictions automatically
            outcome = self.graph.supersede_and_add(
                subject_id=fact.subject,
                predicate=fact.predicate,
                object_id=fact.object_id,
                object_literal=fact.object_literal,
                source_episode_id=source_episode_id,
                valid_from=fact.valid_from,
                valid_to=fact.valid_to,
                confidence=fact.confidence,
            )
            facts_added += 1
            if outcome["superseded"]:
                contradictions_found += len(outcome["superseded"])

        return {
            "entities_added": entities_added,
            "facts_added": facts_added,
            "contradictions_found": contradictions_found,
            "graph_stats": self.graph.stats(),
        }

    def build_communities(
        self,
        max_clusters: int = 10,
        summarize: bool = True,
    ) -> dict:
        """Cluster facts (or episodic chunks) into topic communities.

        If the knowledge graph has facts, clusters those. Otherwise,
        falls back to clustering episodic chunks by embedding similarity.
        """
        # Try graph facts first
        clusters = cluster_facts(
            self.graph,
            max_clusters=max_clusters,
        )

        # Fallback: cluster episodic chunks if graph is empty
        if not clusters:
            clusters = self._cluster_episodic_chunks(max_clusters=max_clusters)

        if summarize:
            clusters = summarize_clusters(clusters, self.graph)

        # Store clusters
        self.community = CommunityStore()
        for cluster in clusters:
            self.community.add_cluster(cluster)

        return {
            "num_clusters": len(clusters),
            "total_facts_in_clusters": self.community.total_facts_in_clusters,
            "cluster_labels": [c.label for c in clusters],
            "graph_stats": self.graph.stats(),
        }

    def _cluster_episodic_chunks(
        self,
        max_clusters: int = 10,
        min_cluster_size: int = 2,
    ) -> list:
        """Cluster episodic chunks by embedding similarity.

        Used as a fallback when the knowledge graph has no facts yet.
        """
        from backend.memory.community import TopicCluster
        import numpy as np

        # Fetch all chunks from ChromaDB
        results = self.store._collection.get(include=["documents", "metadatas"])
        if not results["ids"]:
            return []

        ids = results["ids"]
        docs = results["documents"]
        metadatas = results["metadatas"] or [{}] * len(ids)

        # Group by source_path to create per-document clusters
        sources: dict[str, list[int]] = {}
        for i, meta in enumerate(metadatas):
            src = meta.get("source_path", "unknown") if meta else "unknown"
            sources.setdefault(src, []).append(i)

        # Build clusters from source groups
        clusters = []
        for src, indices in sources.items():
            if len(indices) < min_cluster_size:
                # Merge small groups into a catch-all cluster
                continue

            # Use the first heading or first line as label
            first_text = docs[indices[0]].strip()
            label = "Untitled"
            for line in first_text.split("\n"):
                line = line.strip()
                if line.startswith("#"):
                    label = line.lstrip("# ").strip()
                    break
                elif line and len(line) > 5:
                    label = line[:80]
                    break

            # Build summary from all chunks in this source
            summaries = []
            for idx in indices:
                text = docs[idx].strip()
                if text:
                    summaries.append(text[:200])
            summary = "\n\n".join(summaries[:3])
            if len(summaries) > 3:
                summary += f"\n\n(+ {len(summaries) - 3} more sections)"

            # Compute centroid embedding for search
            chunk_texts = [docs[i].strip() for i in indices if docs[i].strip()]
            if chunk_texts:
                chunk_embs = embed_texts(chunk_texts[:5])  # limit for speed
                centroid = np.mean(chunk_embs, axis=0).tolist()
            else:
                centroid = []

            cluster = TopicCluster(
                cluster_id=f"episodic-{src.replace('/', '_').replace('.', '_')}",
                label=label,
                summary=summary,
                fact_ids=[ids[i] for i in indices],
                entity_ids=[],
                centroid_embedding=centroid,
            )
            clusters.append(cluster)

        # If no cluster met min_cluster_size, create one big cluster
        if not clusters and ids:
            all_text = "\n\n".join(docs[:5])
            chunk_texts = [d.strip() for d in docs[:5] if d.strip()]
            centroid = np.mean(embed_texts(chunk_texts), axis=0).tolist() if chunk_texts else []
            cluster = TopicCluster(
                cluster_id="episodic-all",
                label="All Ingested Content",
                summary=all_text[:500],
                fact_ids=ids,
                entity_ids=[],
                centroid_embedding=centroid,
            )
            clusters = [cluster]

        return clusters[:max_clusters]

    def _process_capture(
        self,
        capture: Capture,
        *,
        extract: bool = False,
    ) -> dict:
        """Chunk → embed → store, optionally extract → graph."""
        # 1. Chunk
        chunks = chunk_text(
            capture.content,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            capture_id=capture.capture_id,
        )
        if not chunks:
            return {"num_chunks": 0, "doc_ids": []}

        # 2. Embed
        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts)

        # 3. Store in ChromaDB
        doc_ids = self.store.add_chunks(
            chunks,
            embeddings,
            source_path=capture.source_path,
            source_type=capture.source_type,
            extra_metadata=capture.metadata,
        )

        # 4. Index in BM25
        for doc_id, chunk in zip(doc_ids, chunks):
            self.bm25.add(doc_id, chunk.text, {"capture_id": capture.capture_id})

        result: dict = {
            "num_chunks": len(chunks),
            "doc_ids": doc_ids,
        }

        # 5. (Phase 2) Extract entities + facts via LLM
        if extract:
            # Use the full capture content for extraction (not individual chunks)
            try:
                extraction = self.extractor.extract(
                    capture.content,
                    source_context=capture.source_path,
                )

                # Store entities
                for ent in extraction.entities:
                    self.graph.add_entity(ent.entity_id, ent.label, ent.entity_type)

                # Store facts with automatic contradiction handling
                for fact in extraction.facts:
                    self.graph.supersede_and_add(
                        subject_id=fact.subject,
                        predicate=fact.predicate,
                        object_id=fact.object_id,
                        object_literal=fact.object_literal,
                        source_episode_id=capture.capture_id,
                        valid_from=fact.valid_from,
                        valid_to=fact.valid_to,
                        confidence=fact.confidence,
                    )

                result["extraction"] = extraction
            except Exception as e:
                logger.warning(f"Extraction failed for {capture.source_path}: {e}")
                result["extraction_error"] = str(e)

        return result
