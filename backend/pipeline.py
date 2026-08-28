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
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)

# Adapter registry — maps source types to adapter classes
ADAPTERS: dict[str, type[IngestionAdapter]] = {
    "markdown": MarkdownAdapter,
    "pdf": PDFAdapter,
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
        extractor: FactExtractor | None = None,
    ):
        self.store = episodic_store or EpisodicStore()
        self.bm25 = bm25_index or BM25Index()
        self.graph = graph or TemporalGraph()
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
