"""Real-data seeds and golden queries derived from the wiki articles.

Entities and facts extracted from:
  - local-first-software
  - graph-rag
  - hybrid-retrieval
  - karpathy-pattern
  - ai-agents
  - compound-knowledge
  - sample_vault (ai-memory, temporal-databases)
"""

from backend.eval.golden_set import GoldenQuery


# ── Real entities extracted from wiki ────────────────────────────────

REAL_ENTITIES = [
    # Concepts
    {"id": "local_first_software", "label": "Local-First Software", "type": "concept"},
    {"id": "graph_rag", "label": "Graph RAG", "type": "concept"},
    {"id": "hybrid_retrieval", "label": "Hybrid Retrieval", "type": "concept"},
    {"id": "karpathy_pattern", "label": "Karpathy Pattern", "type": "concept"},
    {"id": "ai_agents", "label": "AI Agents", "type": "concept"},
    {"id": "compound_knowledge", "label": "Compound Knowledge", "type": "concept"},
    {"id": "bi_temporal_modeling", "label": "Bi-Temporal Modeling", "type": "concept"},
    {"id": "episodic_memory", "label": "Episodic Memory", "type": "concept"},
    {"id": "semantic_memory", "label": "Semantic Memory", "type": "concept"},
    {"id": "memory_consolidation", "label": "Memory Consolidation", "type": "concept"},
    {"id": "rag", "label": "RAG", "type": "concept"},
    {"id": "vector_search", "label": "Vector Search", "type": "concept"},
    {"id": "bm25", "label": "BM25", "type": "concept"},
    {"id": "rrf", "label": "Reciprocal Rank Fusion", "type": "concept"},
    {"id": "knowledge_graph", "label": "Knowledge Graph", "type": "concept"},
    {"id": "flywheel_effect", "label": "Flywheel Effect", "type": "concept"},
    {"id": "librarian_pattern", "label": "Librarian Pattern", "type": "concept"},
    # Tools / Technologies
    {"id": "obsidian", "label": "Obsidian", "type": "tool"},
    {"id": "neo4j", "label": "Neo4j", "type": "tool"},
    {"id": "chromadb", "label": "ChromaDB", "type": "tool"},
    {"id": "networkx", "label": "NetworkX", "type": "tool"},
    {"id": "graphiti", "label": "Graphiti", "type": "tool"},
    {"id": "sentence_transformers", "label": "sentence-transformers", "type": "tool"},
    {"id": "fastapi", "label": "FastAPI", "type": "tool"},
    {"id": "nicegui", "label": "NiceGUI", "type": "tool"},
    # People / Organizations
    {"id": "karpathy", "label": "Andrej Karpathy", "type": "person"},
    {"id": "zep_ai", "label": "Zep AI", "type": "organization"},
    # Techniques
    {"id": "wiki_links", "label": "Wiki Links", "type": "technique"},
    {"id": "cross_encoder", "label": "Cross-Encoder Reranking", "type": "technique"},
    {"id": "ner", "label": "Named Entity Recognition", "type": "technique"},
]


# ── Real facts extracted from wiki ──────────────────────────────────

REAL_FACTS = [
    # Local-first
    {"subject": "local_first_software", "predicate": "enables",
     "object_id": "karpathy_pattern",
     "valid_from": "2026-01-01",
     "recorded_at": "2026-08-01T00:00:00Z"},

    {"subject": "local_first_software", "predicate": "enables",
     "object_id": "ai_agents",
     "valid_from": "2026-01-01",
     "recorded_at": "2026-08-01T00:00:00Z"},

    {"subject": "local_first_software", "predicate": "enables",
     "object_id": "graph_rag",
     "valid_from": "2026-01-01",
     "recorded_at": "2026-08-01T00:00:00Z"},

    {"subject": "local_first_software", "predicate": "uses",
     "object_id": "wiki_links",
     "valid_from": "2026-01-01"},

    {"subject": "local_first_software", "predicate": "implements",
     "object_id": "obsidian",
     "valid_from": "2026-01-01"},

    # Graph RAG
    {"subject": "graph_rag", "predicate": "extends",
     "object_id": "rag",
     "valid_from": "2025-01-01",
     "recorded_at": "2026-08-01T00:00:00Z"},

    {"subject": "graph_rag", "predicate": "uses",
     "object_id": "knowledge_graph",
     "valid_from": "2025-01-01"},

    {"subject": "graph_rag", "predicate": "retrieves_by",
     "object_literal": "relationship rather than similarity",
     "valid_from": "2025-01-01"},

    {"subject": "graph_rag", "predicate": "enables",
     "object_id": "ai_agents",
     "valid_from": "2026-01-01"},

    # Hybrid retrieval
    {"subject": "hybrid_retrieval", "predicate": "combines",
     "object_id": "graph_rag",
     "valid_from": "2026-01-01",
     "recorded_at": "2026-08-01T00:00:00Z"},

    {"subject": "hybrid_retrieval", "predicate": "combines",
     "object_id": "vector_search",
     "valid_from": "2026-01-01"},

    {"subject": "hybrid_retrieval", "predicate": "combines",
     "object_id": "bm25",
     "valid_from": "2026-01-01"},

    {"subject": "hybrid_retrieval", "predicate": "uses",
     "object_id": "rrf",
     "valid_from": "2026-01-01"},

    {"subject": "rrf", "predicate": "is_a",
     "object_literal": "most robust fusion strategy for combining ranked lists",
     "valid_from": "2026-01-01"},

    # Karpathy pattern
    {"subject": "karpathy_pattern", "predicate": "proposed_by",
     "object_id": "karpathy",
     "valid_from": "2025-01-01"},

    {"subject": "karpathy_pattern", "predicate": "avoids",
     "object_id": "vector_search",
     "valid_from": "2025-01-01"},

    {"subject": "karpathy_pattern", "predicate": "uses",
     "object_id": "local_first_software",
     "valid_from": "2025-01-01"},

    {"subject": "karpathy_pattern", "predicate": "enables",
     "object_id": "ai_agents",
     "valid_from": "2025-01-01"},

    # AI Agents
    {"subject": "ai_agents", "predicate": "implements",
     "object_id": "librarian_pattern",
     "valid_from": "2026-01-01"},

    {"subject": "ai_agents", "predicate": "uses",
     "object_id": "local_first_software",
     "valid_from": "2026-01-01"},

    {"subject": "ai_agents", "predicate": "maintains",
     "object_id": "knowledge_graph",
     "valid_from": "2026-01-01"},

    {"subject": "ai_agents", "predicate": "enables",
     "object_id": "compound_knowledge",
     "valid_from": "2026-01-01"},

    # Compound knowledge
    {"subject": "compound_knowledge", "predicate": "depends_on",
     "object_id": "local_first_software",
     "valid_from": "2026-01-01"},

    {"subject": "compound_knowledge", "predicate": "depends_on",
     "object_id": "graph_rag",
     "valid_from": "2026-01-01"},

    {"subject": "compound_knowledge", "predicate": "depends_on",
     "object_id": "ai_agents",
     "valid_from": "2026-01-01"},

    {"subject": "compound_knowledge", "predicate": "creates",
     "object_id": "flywheel_effect",
     "valid_from": "2026-01-01"},

    # Graphiti
    {"subject": "graphiti", "predicate": "created_by",
     "object_id": "zep_ai",
     "valid_from": "2025-01-01"},

    {"subject": "graphiti", "predicate": "implements",
     "object_id": "bi_temporal_modeling",
     "valid_from": "2025-01-01"},

    {"subject": "graphiti", "predicate": "uses",
     "object_id": "knowledge_graph",
     "valid_from": "2025-01-01"},

    # Bi-temporal modeling
    {"subject": "bi_temporal_modeling", "predicate": "tracks",
     "object_literal": "valid time and recorded time",
     "valid_from": "2026-01-01"},

    {"subject": "bi_temporal_modeling", "predicate": "enables",
     "object_literal": "point-in-time queries about beliefs",
     "valid_from": "2026-01-01"},

    # Memory concepts
    {"subject": "episodic_memory", "predicate": "stores",
     "object_literal": "raw experiences with timestamps",
     "valid_from": "2026-01-01"},

    {"subject": "semantic_memory", "predicate": "stores",
     "object_literal": "generalized facts and relationships",
     "valid_from": "2026-01-01"},

    {"subject": "memory_consolidation", "predicate": "clusters",
     "object_id": "episodic_memory",
     "valid_from": "2026-01-01"},

    {"subject": "memory_consolidation", "predicate": "extracts",
     "object_id": "semantic_memory",
     "valid_from": "2026-01-01"},

    # Neo4j
    {"subject": "neo4j", "predicate": "supports",
     "object_id": "bi_temporal_modeling",
     "valid_from": "2025-01-01"},

    {"subject": "neo4j", "predicate": "uses",
     "object_literal": "APOC procedures for temporal queries",
     "valid_from": "2025-01-01"},

    # Wiki links
    {"subject": "wiki_links", "predicate": "create",
     "object_literal": "implicit graph edges between articles",
     "valid_from": "2026-01-01"},

    {"subject": "wiki_links", "predicate": "used_by",
     "object_id": "local_first_software",
     "valid_from": "2026-01-01"},
]


# ── Real golden queries ─────────────────────────────────────────────

REAL_GOLDEN_QUERIES: list[GoldenQuery] = [
    # Single-hop: direct facts
    GoldenQuery(
        query="What does local-first software enable?",
        query_type="single_hop",
        expected_entities=["local_first_software"],
        expected_predicates=["enables"],
        expected_answer_contains=["karpathy_pattern", "ai_agents", "graph_rag"],
        difficulty="easy",
        notes="From local-first-software article: enables karpathy pattern, agents, and graph RAG",
    ),
    GoldenQuery(
        query="Who proposed the Karpathy pattern?",
        query_type="single_hop",
        expected_entities=["karpathy_pattern"],
        expected_predicates=["proposed_by"],
        expected_answer_contains=["karpathy", "andrej"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What does hybrid retrieval combine?",
        query_type="single_hop",
        expected_entities=["hybrid_retrieval"],
        expected_predicates=["combines"],
        expected_answer_contains=["graph", "vector", "bm25"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What does Graphiti implement?",
        query_type="single_hop",
        expected_entities=["graphiti"],
        expected_predicates=["implements"],
        expected_answer_contains=["bi-temporal", "temporal"],
        difficulty="easy",
    ),
    GoldenQuery(
        query="What fusion strategy does hybrid retrieval use?",
        query_type="single_hop",
        expected_entities=["hybrid_retrieval"],
        expected_predicates=["uses"],
        expected_answer_contains=["rrf", "reciprocal", "rank"],
        difficulty="easy",
    ),

    # Multi-hop: follow 2+ edges
    GoldenQuery(
        query="What does the Karpathy pattern avoid using?",
        query_type="multi_hop",
        expected_entities=["karpathy_pattern"],
        expected_predicates=["avoids"],
        expected_answer_contains=["vector", "embedding"],
        difficulty="medium",
        notes="Direct: karpathy_pattern avoids vector_search",
    ),
    GoldenQuery(
        query="What tools does the approach proposed by Andrej Karpathy depend on?",
        query_type="multi_hop",
        expected_entities=["karpathy", "karpathy_pattern"],
        expected_predicates=["proposed_by", "uses"],
        expected_answer_contains=["local_first_software", "obsidian", "markdown"],
        difficulty="medium",
        notes="karpathy → proposed_by → karpathy_pattern → uses → local_first_software → uses → obsidian",
    ),
    GoldenQuery(
        query="What does Graph RAG extend, and what does that extended system use for lexical matching?",
        query_type="multi_hop",
        expected_entities=["graph_rag", "rag"],
        expected_predicates=["extends", "uses"],
        expected_answer_contains=["bm25"],
        difficulty="medium",
        notes="graph_rag → extends → rag → (rag uses bm25 from hybrid_retrieval)",
    ),
    GoldenQuery(
        query="What maintains the knowledge graph that AI agents use?",
        query_type="multi_hop",
        expected_entities=["ai_agents", "knowledge_graph"],
        expected_predicates=["maintains", "uses"],
        expected_answer_contains=["ai_agents"],
        difficulty="medium",
        notes="ai_agents maintains knowledge_graph",
    ),

    # Point-in-time
    GoldenQuery(
        query="What did the system record about Graphiti's capabilities as of 2025?",
        query_type="point_in_time",
        expected_entities=["graphiti"],
        expected_predicates=["implements", "uses"],
        expected_answer_contains=["bi-temporal", "knowledge_graph"],
        difficulty="medium",
    ),
    GoldenQuery(
        query="Show me all facts about Karpathy that were recorded before August 2026",
        query_type="point_in_time",
        expected_entities=["karpathy", "karpathy_pattern"],
        expected_predicates=["proposed_by"],
        expected_answer_contains=["karpathy"],
        difficulty="medium",
    ),

    # Contradiction / evolution
    GoldenQuery(
        query="Does the system treat vector search as essential or optional for knowledge routing?",
        query_type="contradiction",
        expected_entities=["karpathy_pattern", "vector_search"],
        expected_predicates=["avoids"],
        expected_answer_contains=["avoids", "vector"],
        difficulty="hard",
        notes="Karpathy pattern avoids vector_search, but hybrid_retrieval combines it — tension in the corpus",
    ),
    GoldenQuery(
        query="How do the views on retrieval methods differ between the Karpathy pattern and hybrid retrieval approaches?",
        query_type="contradiction",
        expected_entities=["karpathy_pattern", "hybrid_retrieval"],
        expected_predicates=["avoids", "combines"],
        expected_answer_contains=["vector", "karpathy"],
        difficulty="hard",
        notes="Karpathy avoids vectors, hybrid combines them — complementary but different philosophy",
    ),

    # Episodic: match actual text from notes
    GoldenQuery(
        query="What is the problem with cloud-first software according to the notes?",
        query_type="episodic",
        expected_answer_contains=["vendor lock-in", "latency", "privacy"],
        difficulty="easy",
        notes="From local-first-software article",
    ),
    GoldenQuery(
        query="What are the three types of value in the compound knowledge flywheel?",
        query_type="episodic",
        expected_answer_contains=["storage", "retrieval", "synthesis"],
        difficulty="easy",
        notes="From compound-knowledge-flywheel.md",
    ),
    GoldenQuery(
        query="What SQL standard introduced temporal features?",
        query_type="episodic",
        expected_answer_contains=["sql:2011", "sql 2011"],
        difficulty="easy",
        notes="From temporal-databases.md",
    ),
    GoldenQuery(
        query="What are the two timelines tracked by bi-temporal data models?",
        query_type="episodic",
        expected_answer_contains=["valid time", "recorded time"],
        difficulty="easy",
        notes="From ai-memory.md",
    ),
]


def get_real_seeds() -> list[dict]:
    """Return entity + fact seeds for the real wiki content."""
    seeds = []
    for e in REAL_ENTITIES:
        seeds.append({"entity": e})
    for f in REAL_FACTS:
        seeds.append({"fact": f})
    return seeds


def get_real_golden_set(
    query_type: str | None = None,
    difficulty: str | None = None,
) -> list[GoldenQuery]:
    """Return the real-data golden query set, optionally filtered."""
    queries = REAL_GOLDEN_QUERIES
    if query_type:
        queries = [q for q in queries if q.query_type == query_type]
    if difficulty:
        queries = [q for q in queries if q.difficulty == difficulty]
    return queries
