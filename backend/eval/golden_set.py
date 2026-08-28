"""Golden query set for evaluating the second-brain system.

Each query is tagged by type:
  - single_hop: answer found by 1 entity lookup + direct fact
  - multi_hop: requires following 2+ edges in the graph
  - point_in_time: asks about facts valid at a specific date
  - contradiction: asks the system to detect conflicting facts
  - episodic: should match raw text from the episodic store
  - community: tests topic-level summarization (Phase 5)

Each entry carries:
  - query: natural language question
  - query_type: one of the types above
  - expected_entities: entity_ids that should appear in the answer path
  - expected_predicates: predicates that should be traversed
  - expected_answer_contains: substring(s) the answer should mention
  - setup: optional list of facts to seed the graph before evaluation
  - difficulty: "easy" | "medium" | "hard"
"""

from dataclasses import dataclass, field


@dataclass
class GoldenQuery:
    query: str
    query_type: str
    expected_entities: list[str] = field(default_factory=list)
    expected_predicates: list[str] = field(default_factory=list)
    expected_answer_contains: list[str] = field(default_factory=list)
    setup: list[dict] = field(default_factory=list)
    difficulty: str = "medium"
    notes: str = ""


# ── Setup seeds: reusable entity/fact blocks ────────────────────────

DEFAULT_SEEDS: list[dict] = [
    # Entities
    {"entity": {"id": "user", "label": "Ayush", "type": "person"}},
    {"entity": {"id": "rag", "label": "RAG", "type": "concept"}},
    {"entity": {"id": "graph_rag", "label": "Graph RAG", "type": "concept"}},
    {"entity": {"id": "networkx", "label": "NetworkX", "type": "tool"}},
    {"entity": {"id": "neo4j", "label": "Neo4j", "type": "tool"}},
    {"entity": {"id": "chromadb", "label": "ChromaDB", "type": "tool"}},
    {"entity": {"id": "bm25", "label": "BM25", "type": "technique"}},
    {"entity": {"id": "sentence_transformers", "label": "sentence-transformers", "type": "tool"}},
    {"entity": {"id": "second_brain", "label": "Second Brain Project", "type": "concept"}},
    {"entity": {"id": "bi_temporal", "label": "Bi-Temporal Modeling", "type": "concept"}},
    {"entity": {"id": "knowledge_graph", "label": "Knowledge Graph", "type": "concept"}},
    {"entity": {"id": "claude", "label": "Claude", "type": "tool"}},
    {"entity": {"id": "obsidian", "label": "Obsidian", "type": "tool"}},
    {"entity": {"id": "fastapi", "label": "FastAPI", "type": "tool"}},
    {"entity": {"id": "hybrid_retrieval", "label": "Hybrid Retrieval", "type": "technique"}},
    # Facts with temporal windows
    {"fact": {"subject": "user", "predicate": "works_on", "object_id": "second_brain",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "user", "predicate": "uses", "object_id": "networkx",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "user", "predicate": "uses", "object_id": "chromadb",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "user", "predicate": "uses", "object_id": "fastapi",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "user", "predicate": "uses", "object_id": "claude",
              "valid_from": "2026-03-01"}},
    {"fact": {"subject": "user", "predicate": "uses", "object_id": "sentence_transformers",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "second_brain", "predicate": "implements", "object_id": "bi_temporal",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "second_brain", "predicate": "uses", "object_id": "knowledge_graph",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "second_brain", "predicate": "built_with", "object_id": "fastapi",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "rag", "predicate": "uses", "object_id": "bm25",
              "valid_from": "2025-01-01"}},
    {"fact": {"subject": "rag", "predicate": "uses", "object_id": "sentence_transformers",
              "valid_from": "2025-01-01"}},
    {"fact": {"subject": "graph_rag", "predicate": "extends", "object_id": "rag",
              "valid_from": "2025-06-01"}},
    {"fact": {"subject": "graph_rag", "predicate": "uses", "object_id": "knowledge_graph",
              "valid_from": "2025-06-01"}},
    {"fact": {"subject": "hybrid_retrieval", "predicate": "combines", "object_id": "bm25",
              "valid_from": "2026-01-01"}},
    {"fact": {"subject": "hybrid_retrieval", "predicate": "combines", "object_id": "rag",
              "valid_from": "2026-01-01"}},
    # Beliefs that change over time (for contradiction testing)
    {"fact": {"subject": "user", "predicate": "believes",
              "object_literal": "NetworkX is sufficient for the knowledge graph",
              "valid_from": "2026-01-01", "valid_to": "2026-06-30",
              "recorded_at": "2026-01-15T00:00:00Z"}},
    {"fact": {"subject": "user", "predicate": "believes",
              "object_literal": "Neo4j would be better for scale than NetworkX",
              "valid_from": "2026-07-01",
              "recorded_at": "2026-07-10T00:00:00Z"}},
    {"fact": {"subject": "user", "predicate": "believes",
              "object_literal": "BM25 alone is enough for lexical search",
              "valid_from": "2026-01-01", "valid_to": "2026-04-30",
              "recorded_at": "2026-02-01T00:00:00Z"}},
    {"fact": {"subject": "user", "predicate": "believes",
              "object_literal": "Hybrid retrieval with RRF outperforms BM25 alone",
              "valid_from": "2026-05-01",
              "recorded_at": "2026-05-15T00:00:00Z"}},
]


# ── Golden queries ──────────────────────────────────────────────────

GOLDEN_QUERIES: list[GoldenQuery] = [
    # ── Single-hop ──────────────────────────────────────────────────
    GoldenQuery(
        query="What tools does Ayush use?",
        query_type="single_hop",
        expected_entities=["user"],
        expected_predicates=["uses"],
        expected_answer_contains=["networkx", "chromadb", "fastapi", "claude"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What does the Second Brain project implement?",
        query_type="single_hop",
        expected_entities=["second_brain"],
        expected_predicates=["implements"],
        expected_answer_contains=["bi-temporal"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What technology does RAG use for lexical search?",
        query_type="single_hop",
        expected_entities=["rag"],
        expected_predicates=["uses"],
        expected_answer_contains=["bm25"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What is Graph RAG built on top of?",
        query_type="single_hop",
        expected_entities=["graph_rag"],
        expected_predicates=["extends"],
        expected_answer_contains=["rag"],
        difficulty="easy",
    ),

    # ── Multi-hop ───────────────────────────────────────────────────
    GoldenQuery(
        query="What tools are used in the technologies that RAG combines with?",
        query_type="multi_hop",
        expected_entities=["rag", "hybrid_retrieval"],
        expected_predicates=["combines", "uses"],
        expected_answer_contains=["bm25", "sentence_transformers"],
        difficulty="medium",
    ),
    GoldenQuery(
        query="What does Ayush's project use that extends RAG?",
        query_type="multi_hop",
        expected_entities=["second_brain", "graph_rag", "rag"],
        expected_predicates=["uses", "extends"],
        expected_answer_contains=["knowledge_graph"],
        difficulty="medium",
    ),
    GoldenQuery(
        query="What is the relationship between Hybrid Retrieval and the technologies RAG uses?",
        query_type="multi_hop",
        expected_entities=["hybrid_retrieval", "rag"],
        expected_predicates=["combines", "uses"],
        expected_answer_contains=["bm25"],
        difficulty="medium",
    ),

    # ── Point-in-time ───────────────────────────────────────────────
    GoldenQuery(
        query="What did Ayush believe about NetworkX as of March 2026?",
        query_type="point_in_time",
        expected_entities=["user"],
        expected_predicates=["believes"],
        expected_answer_contains=["sufficient"],
        difficulty="medium",
    ),
    GoldenQuery(
        query="What did Ayush believe about search in January 2026?",
        query_type="point_in_time",
        expected_entities=["user"],
        expected_predicates=["believes"],
        expected_answer_contains=["bm25", "enough"],
        difficulty="medium",
    ),
    GoldenQuery(
        query="What did Ayush believe about search in June 2026?",
        query_type="point_in_time",
        expected_entities=["user"],
        expected_predicates=["believes"],
        expected_answer_contains=["hybrid", "rrf"],
        difficulty="medium",
    ),
    GoldenQuery(
        query="Show me all active beliefs as of August 2026",
        query_type="point_in_time",
        expected_entities=["user"],
        expected_predicates=["believes"],
        expected_answer_contains=["neo4j", "hybrid"],
        difficulty="easy",
    ),

    # ── Contradiction ───────────────────────────────────────────────
    GoldenQuery(
        query="What are the contradictions in Ayush's beliefs about graph storage?",
        query_type="contradiction",
        expected_entities=["user"],
        expected_predicates=["believes"],
        expected_answer_contains=["networkx", "neo4j"],
        difficulty="hard",
    ),
    GoldenQuery(
        query="Has Ayush's view on lexical search changed over time?",
        query_type="contradiction",
        expected_entities=["user"],
        expected_predicates=["believes"],
        expected_answer_contains=["bm25", "hybrid"],
        difficulty="hard",
    ),

    # ── Episodic ────────────────────────────────────────────────────
    GoldenQuery(
        query="Find notes about bi-temporal modeling",
        query_type="episodic",
        expected_answer_contains=["bi-temporal", "temporal"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What notes mention ChromaDB?",
        query_type="episodic",
        expected_answer_contains=["chromadb"],
        difficulty="easy",
    ),
]


def get_golden_set(
    query_type: str | None = None,
    difficulty: str | None = None,
) -> list[GoldenQuery]:
    """Return the golden query set, optionally filtered."""
    queries = GOLDEN_QUERIES
    if query_type:
        queries = [q for q in queries if q.query_type == query_type]
    if difficulty:
        queries = [q for q in queries if q.difficulty == difficulty]
    return queries


def get_all_query_types() -> list[str]:
    """Return all unique query types in the golden set."""
    return sorted(set(q.query_type for q in GOLDEN_QUERIES))
