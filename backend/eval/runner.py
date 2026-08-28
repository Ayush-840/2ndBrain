"""Eval runner: executes golden queries against the pipeline and scores them.

Sets up a temporary graph with seeded facts, runs each query through
the hybrid retriever, and produces scored results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.eval.golden_set import GoldenQuery, get_golden_set, DEFAULT_SEEDS
from backend.eval.scorer import (
    QueryScore,
    EvalResult,
    score_query,
    aggregate_results,
    save_results,
)
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.retrieval.bm25 import BM25Index
from backend.retrieval.hybrid import HybridRetriever
from backend.retrieval.graph_retrieval import GraphRetriever

logger = logging.getLogger(__name__)


def seed_graph(graph: TemporalGraph, seeds: list[dict] | None = None) -> None:
    """Populate a graph with seed entities and facts."""
    seeds = seeds or DEFAULT_SEEDS

    for item in seeds:
        if "entity" in item:
            e = item["entity"]
            graph.add_entity(e["id"], e["label"], e["type"])

        if "fact" in item:
            f = item["fact"]
            graph.add_fact(
                f["subject"],
                f["predicate"],
                object_id=f.get("object_id"),
                object_literal=f.get("object_literal"),
                source_episode_id=f.get("source_episode_id", ""),
                valid_from=f.get("valid_from"),
                valid_to=f.get("valid_to"),
                recorded_at=f.get("recorded_at"),
                confidence=f.get("confidence", 1.0),
            )


def extract_entities_from_results(
    results: list,
    graph: TemporalGraph,
) -> tuple[list[str], list[str]]:
    """Extract entity IDs and predicates mentioned in search results."""
    entities: set[str] = set()
    predicates: set[str] = set()

    for r in results:
        # From metadata
        meta = r.metadata if hasattr(r, "metadata") else {}
        if meta.get("matched_entity"):
            entities.add(meta["matched_entity"])

        # From graph results (source contains "graph")
        source = r.source if hasattr(r, "source") else ""
        if "graph" in source:
            # Try to extract from text
            text = r.text if hasattr(r, "text") else ""
            # Check if the text matches any known entity
            for ent in graph.list_entities():
                eid = ent.get("entity_id")
                if not eid:
                    continue
                if ent["label"].lower() in text.lower():
                    entities.add(eid)

            # Extract predicates from text
            for fact in graph.query_all_facts():
                pred = fact.get("predicate", "")
                if pred.replace("_", " ") in text.lower():
                    predicates.add(pred)

        # For graph results, also check the id (fact_id)
        if "graph" in source:
            fact_id = r.id if hasattr(r, "id") else ""
            fact = graph.get_fact(fact_id)
            if fact:
                predicates.add(fact.get("predicate", ""))
                entities.add(fact.get("subject", ""))
                obj = fact.get("object", "")
                if not obj.startswith("_literal:"):
                    entities.add(obj)

    return list(entities), list(predicates)


@dataclass
class EvalConfig:
    """Configuration for an eval run."""

    seeds: list[dict] | None = None
    episodic_chunks: list[dict] | None = None  # optional text chunks to seed episodic store
    top_k: int = 10
    save_path: str = "data/eval_results.json"


def run_eval(
    config: EvalConfig | None = None,
    query_type: str | None = None,
    difficulty: str | None = None,
    verbose: bool = False,
) -> EvalResult:
    """Run the full evaluation.

    1. Set up a temporary graph with seeded facts
    2. Run each golden query through the hybrid retriever
    3. Score results against expectations
    4. Aggregate and return

    Args:
        config: Eval configuration. Uses defaults if None.
        query_type: Filter golden set to this type.
        difficulty: Filter golden set to this difficulty.
        verbose: Print per-query results.
    """
    config = config or EvalConfig()

    # Set up stores
    graph = TemporalGraph()
    seed_graph(graph, config.seeds)

    # Episodic store — in-memory for eval (uses temp dir)
    import tempfile
    tmpdir = tempfile.mkdtemp()
    store = EpisodicStore(persist_dir=tmpdir)
    bm25 = BM25Index()

    # Seed episodic store if provided
    if config.episodic_chunks:
        from backend.enrichment.chunker import Chunk
        from backend.enrichment.embedder import embed_texts

        chunks = []
        texts = []
        for i, item in enumerate(config.episodic_chunks):
            chunks.append(
                Chunk(
                    text=item["text"],
                    chunk_index=i,
                    source_capture_id=item.get("capture_id", "eval"),
                    start_offset=0,
                    end_offset=len(item["text"]),
                )
            )
            texts.append(item["text"])

        if texts:
            embeddings = embed_texts(texts)
            doc_ids = store.add_chunks(chunks, embeddings, source_path="/eval.md")
            for doc_id, chunk in zip(doc_ids, chunks):
                bm25.add(doc_id, chunk.text)

    # Build retriever
    retriever = HybridRetriever(
        episodic_store=store,
        bm25_index=bm25,
        graph=graph,
    )

    # Get golden queries
    golden_queries = get_golden_set(query_type=query_type, difficulty=difficulty)

    # Run each query
    scores: list[QueryScore] = []

    for golden in golden_queries:
        if verbose:
            print(f"\n{'='*60}")
            print(f"Q: {golden.query}")
            print(f"  Type: {golden.query_type}, Difficulty: {golden.difficulty}")

        # Run the query
        results = retriever.search(
            golden.query,
            top_k=config.top_k,
        )

        # Extract text and metadata
        result_texts = [r.text for r in results]
        result_metadatas = [r.metadata for r in results]
        result_sources = [r.source for r in results]

        # Extract entity/predicate mentions
        found_entities, found_predicates = extract_entities_from_results(results, graph)

        # Score
        score = score_query(
            golden,
            result_texts,
            result_metadatas,
            result_sources,
            found_entities=found_entities,
            found_predicates=found_predicates,
        )
        scores.append(score)

        if verbose:
            print(f"  Overall: {score.overall:.2f}")
            print(f"  Entity recall: {score.entity_recall:.2f} "
                  f"(found: {score.found_entities}, missed: {score.answer_misses})")
            print(f"  Predicate recall: {score.predicate_recall:.2f}")
            print(f"  Answer relevance: {score.answer_relevance:.2f} "
                  f"(matched: {score.answer_matches}, missed: {score.answer_misses})")
            if result_texts:
                print(f"  Top result: {result_texts[0][:100]}...")

    # Aggregate
    eval_result = aggregate_results(scores)

    # Save
    if config.save_path:
        save_results(eval_result, config.save_path)
        if verbose:
            print(f"\nResults saved to {config.save_path}")

    return eval_result
