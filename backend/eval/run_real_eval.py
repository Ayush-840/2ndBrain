#!/usr/bin/env python3
"""Run the eval harness against real wiki content.

Seeds the graph with entities and facts extracted from the actual wiki articles,
then runs the real-data golden queries and reports results.
"""

import json
import tempfile
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.eval.golden_set import GoldenQuery
from backend.eval.real_data_seeds import get_real_seeds, get_real_golden_set, REAL_ENTITIES, REAL_FACTS
from backend.eval.runner import seed_graph, extract_entities_from_results
from backend.eval.scorer import (
    score_query,
    aggregate_results,
    save_results,
    QueryScore,
)
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.retrieval.bm25 import BM25Index
from backend.retrieval.hybrid import HybridRetriever


def run_real_eval(verbose: bool = True):
    """Run eval with real wiki data."""
    print("=" * 70)
    print("2ndBrain Real-Data Evaluation")
    print("=" * 70)
    print()

    # ── 1. Set up graph with real facts ──────────────────────────────
    print("Setting up graph with real wiki data...")
    graph = TemporalGraph()
    seeds = get_real_seeds()
    seed_graph(graph, seeds)
    stats = graph.stats()
    print(f"  Entities: {stats['entities']}")
    print(f"  Facts: {stats['facts']}")
    print(f"  Active facts: {stats['active_facts']}")
    print()

    # ── 2. Set up episodic store with wiki text ──────────────────────
    print("Loading wiki articles into episodic store...")
    tmpdir = tempfile.mkdtemp()
    store = EpisodicStore(persist_dir=tmpdir)
    bm25 = BM25Index()

    wiki_files = list(Path("second-brain/wiki").rglob("*.md"))
    vault_files = list(Path("data/sample_vault").rglob("*.md"))
    all_files = wiki_files + vault_files

    from backend.enrichment.chunker import Chunk
    from backend.enrichment.embedder import embed_texts

    all_chunks = []
    all_texts = []
    for filepath in all_files:
        text = filepath.read_text(encoding="utf-8")
        chunks = Chunk.__new__(Chunk)
        # Simple chunking for eval
        chunk_size = 512
        overlap = 64
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if len(chunk_text) >= 50:
                chunk = Chunk(
                    text=chunk_text,
                    chunk_index=idx,
                    source_capture_id=filepath.stem,
                    start_offset=start,
                    end_offset=end,
                )
                all_chunks.append(chunk)
                all_texts.append(chunk_text)
                idx += 1
            start = end - overlap
            if start >= end:
                break

    if all_texts:
        embeddings = embed_texts(all_texts)
        doc_ids = store.add_chunks(all_chunks, embeddings, source_path="/wiki.md")
        for doc_id, chunk in zip(doc_ids, all_chunks):
            bm25.add(doc_id, chunk.text)

    print(f"  Files loaded: {len(all_files)}")
    print(f"  Chunks created: {len(all_chunks)}")
    print(f"  Episodic store: {store.count} chunks")
    print(f"  BM25 index: {bm25.count} documents")
    print()

    # ── 3. Build retriever ───────────────────────────────────────────
    retriever = HybridRetriever(
        episodic_store=store,
        bm25_index=bm25,
        graph=graph,
    )

    # ── 4. Run golden queries ────────────────────────────────────────
    golden_queries = get_real_golden_set()
    print(f"Running {len(golden_queries)} golden queries...")
    print()

    scores: list[QueryScore] = []

    for i, golden in enumerate(golden_queries, 1):
        results = retriever.search(golden.query, top_k=10)

        result_texts = [r.text for r in results]
        result_metadatas = [r.metadata for r in results]
        result_sources = [r.source for r in results]

        found_entities, found_predicates = extract_entities_from_results(results, graph)

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
            status = "✅" if score.overall >= 0.5 else "❌"
            print(f"  {status} [{score.query_type:12s}] [{score.difficulty:6s}] "
                  f"Score: {score.overall:.2f}  |  {golden.query}")
            if score.answer_misses:
                print(f"     Missed: {score.answer_misses}")
            if result_texts:
                # Show top result snippet
                top = result_texts[0][:80]
                print(f"     Top result: {top}...")

    # ── 5. Aggregate and report ──────────────────────────────────────
    print()
    print("=" * 70)
    eval_result = aggregate_results(scores)
    print(eval_result.summary)
    print("=" * 70)

    # Save results
    save_path = "data/eval_real_results.json"
    save_results(eval_result, save_path)
    print(f"\nDetailed results saved to {save_path}")

    # ── 6. Detailed breakdown ────────────────────────────────────────
    print()
    print("Detailed scores per query:")
    print("-" * 70)
    for s in scores:
        parts = []
        if s.entity_recall > 0:
            parts.append(f"entity={s.entity_recall:.0%}")
        if s.predicate_recall > 0:
            parts.append(f"pred={s.predicate_recall:.0%}")
        parts.append(f"answer={s.answer_relevance:.0%}")
        parts.append(f"overall={s.overall:.0%}")
        status = "PASS" if s.overall >= 0.5 else "FAIL"
        print(f"  [{status}] {s.query_type:12s} | {', '.join(parts)} | {s.query}")

    return eval_result


if __name__ == "__main__":
    run_real_eval(verbose=True)
