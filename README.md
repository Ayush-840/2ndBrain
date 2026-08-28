# 2ndBrain — Personal Second Brain with Bi-Temporal Memory

A personal knowledge system that goes beyond traditional RAG. Instead of treating your notes as a static corpus, 2ndBrain builds a **bi-temporal knowledge graph** where facts carry validity windows — so a new belief can supersede an old one without erasing history.

The core idea: **memory that evolves over time**, inspired by the [Graphiti](https://github.com/getzep/graphiti) architecture but implemented from scratch on tools a student can own and explain.

## The Bi-Temporal Model

Every fact in the system carries **two timestamps**:

| Timestamp | Meaning | Example |
|-----------|---------|---------|
| `valid_from` / `valid_to` | When the fact was true **in the world** | "I believed X from Jan 2026 to Mar 2026" |
| `recorded_at` | When the system **learned** the fact | "System learned this on Aug 25, 2026" |

This split enables queries that single-timestamp systems can't answer:
- "What did I believe about X **as of March**?" — filter by `valid_from` ≤ March
- "What **contradicts** what I wrote last week?" — find facts with overlapping valid periods but conflicting predicates
- "Show me **everything relevant** to what I'm working on today" — graph traversal + semantic similarity

When a new fact arrives that conflicts with an existing one, the old fact's `valid_to` is set and a `superseded_by` link is created — **history is never deleted, only refined**.

## Architecture (Five Layers)

```
┌─────────────────────────────────────────────┐
│  Capture          Ingestion adapters        │
│  (markdown, PDF,  ← pluggable sources       │
│   browser clip)                             │
├─────────────────────────────────────────────┤
│  Enrichment      Chunking + embeddings      │
│                   sentence-transformers      │
├─────────────────────────────────────────────┤
│  Memory Store    Three tiers:               │
│                  • Episodic (raw captures)  │
│                  • Semantic (facts + graph) │
│                  • Community (topic clusters)│
├─────────────────────────────────────────────┤
│  Retrieval       Hybrid dense + BM25        │
│                  fused with graph traversal  │
├─────────────────────────────────────────────┤
│  Surface & Act   Contradiction flags        │
│                  Resurfacing, digests        │
└─────────────────────────────────────────────┘
```

**Phase 1** ✅: Episodic store + hybrid retrieval
**Phase 2** ✅: Bi-temporal knowledge graph + Claude extraction
**Phase 3** ✅: 3-way retrieval fusion (dense + BM25 + graph traversal)
**Phase 4** (next): Eval harness with golden query set
**Phase 5**: Surfacing agent (contradiction detection, resurfacing, digests)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI, Python 3.11+ |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector store | ChromaDB (persistent) |
| Lexical search | BM25Okapi (rank_bm25) |
| Graph | NetworkX (swappable to Neo4j) |
| LLM | Claude API (tool calling for extraction) |
| Frontend | React + Vite + Tailwind (Phase 5) |

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run the API
uvicorn backend.main:app --reload

# Ingest your vault (episodic store only)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "data/sample_vault", "source_type": "markdown"}'

# Ingest with LLM extraction (requires BRAIN_ANTHROPIC_API_KEY)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "data/sample_vault", "source_type": "markdown", "extract": true}'

# 3-way hybrid search (dense + BM25 + graph traversal)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is bi-temporal modeling?"}'

# Point-in-time graph query
curl -X POST http://localhost:8000/graph/query-as-of \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-05-01", "predicate": "believes"}'
```

## Project Structure

```
second-brain/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Pydantic settings (env-driven)
│   ├── pipeline.py          # Orchestrator: ingest → chunk → embed → store
│   ├── ingestion/
│   │   ├── base.py          # Abstract IngestionAdapter + Capture dataclass
│   │   ├── markdown.py      # Obsidian-compatible .md adapter
│   │   └── pdf.py           # PyMuPDF-based PDF adapter
│   ├── enrichment/
│   │   ├── chunker.py       # Overlap-based text chunking
│   │   └── embedder.py      # sentence-transformers wrapper
│   ├── memory/
│   │   ├── episodic.py      # ChromaDB episodic store
│   │   └── graph.py         # NetworkX bi-temporal graph
│   ├── retrieval/
│   │   ├── bm25.py          # BM25Okapi lexical search
│   │   ├── hybrid.py        # Dense + BM25 + Graph fusion (3-way RRF)
│   │   └── graph_retrieval.py  # Graph-aware entity extraction + traversal
│   └── api/
│       ├── routes_ingest.py # POST /ingest, /ingest/file, /ingest/url
│       ├── routes_query.py  # POST /query
│       └── routes_graph.py  # POST /graph/query-as-of, /graph/entity, /graph/extract
├── tests/                   # Unit tests (pytest)
├── data/
│   └── sample_vault/        # Sample Obsidian notes for testing
└── pyproject.toml
```

## Running Tests

```bash
pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BRAIN_VAULT_DIR` | `data/sample_vault` | Path to your Obsidian vault |
| `BRAIN_CHROMA_DIR` | `data/chroma` | ChromaDB persistence directory |
| `BRAIN_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `BRAIN_CHUNK_SIZE` | `512` | Characters per chunk |
| `BRAIN_CHUNK_OVERLAP` | `64` | Overlap between adjacent chunks |
| `BRAIN_ANTHROPIC_API_KEY` | — | Claude API key (extraction) |
| `BRAIN_GRAPH_WEIGHT` | `0.2` | Weight for graph results in RRF fusion |
| `BRAIN_GRAPH_HOPS` | `2` | Hops to traverse in graph retrieval |

## Design Decisions

- **PyMuPDF (fitz)** for PDF extraction — fast, pure Python, no system deps
- **Overlap-based chunking** with sentence-boundary awareness — predictable and debuggable
- **ChromaDB as episodic store** — doubles as vector DB and document store; easy to swap
- **BM25 as a standalone index** — keeps lexical search decoupled so it can back to Elasticsearch later
- **NetworkX first, Neo4j later** — clean `TemporalGraph` interface so the swap only touches one module
- **Claude tool calling** for extraction — structured output, no regex parsing
- **Bi-temporal superseding** — new facts close old ones without deleting history
- **RRF for fusion** — the same approach from the Knowledge RAG project, proven to work

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ingest` | Ingest a local file/directory |
| POST | `/ingest/file` | Ingest an uploaded file |
| POST | `/ingest/url` | Ingest a URL/browser clip |
| POST | `/query` | Hybrid search (dense + BM25) |
| POST | `/graph/query-as-of` | Facts valid as of a date |
| POST | `/graph/entity` | Entity neighborhood traversal |
| POST | `/graph/contradictions` | Find contradictions |
| POST | `/graph/extract` | On-demand LLM extraction |
| GET | `/graph/stats` | Graph statistics |
| GET | `/graph/entities` | List all entities |

## License

MIT
