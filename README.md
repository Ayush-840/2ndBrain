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
**Phase 4** ✅: Eval harness with golden query set (86.4% accuracy)
**Phase 5** ✅: Surfacing agent + community memory + NiceGUI frontend

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI, Python 3.11+ |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector store | ChromaDB (persistent) |
| Lexical search | BM25Okapi (rank_bm25) |
| Graph | NetworkX (swappable to Neo4j) |
| LLM | Claude API (tool calling for extraction) |
| Frontend | NiceGUI (pure Python, mounted on FastAPI) |
| Scheduler | APScheduler (daily/weekly surfacing jobs) |

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run with NiceGUI frontend (recommended)
python -m backend.main

# Or run API-only
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

# Build topic communities
curl -X POST http://localhost:8000/community/build

# Generate a daily digest
curl -X POST http://localhost:8000/surfing/digest \
  -H "Content-Type: application/json" \
  -d '{"digest_type": "daily"}'

# Detect contradictions
curl -X POST http://localhost:8000/surfing/contradictions
```

## Project Structure

```
second-brain/
├── backend/
│   ├── main.py              # FastAPI + NiceGUI entry point
│   ├── config.py            # Pydantic settings (env-driven)
│   ├── pipeline.py          # Orchestrator: ingest → chunk → embed → store → community
│   ├── ingestion/
│   │   ├── base.py          # Abstract IngestionAdapter + Capture dataclass
│   │   ├── markdown.py      # Obsidian-compatible .md adapter
│   │   └── pdf.py           # PyMuPDF-based PDF adapter
│   ├── enrichment/
│   │   ├── chunker.py       # Overlap-based text chunking
│   │   ├── embedder.py      # sentence-transformers wrapper
│   │   └── extractor.py     # Claude tool-calling fact extraction
│   ├── memory/
│   │   ├── episodic.py      # ChromaDB episodic store
│   │   ├── graph.py         # NetworkX bi-temporal graph
│   │   └── community.py     # Topic clustering + LLM summarization
│   ├── retrieval/
│   │   ├── bm25.py          # BM25Okapi lexical search
│   │   ├── hybrid.py        # Dense + BM25 + Graph fusion (3-way RRF)
│   │   └── graph_retrieval.py  # Graph-aware entity extraction + traversal
│   ├── surfacing/
│   │   ├── agent.py         # Contradiction detection, resurfacing, digests
│   │   └── scheduler.py     # APScheduler integration
│   ├── eval/
│   │   ├── golden_set.py    # 15 golden queries across 4 types
│   │   ├── runner.py        # Eval execution engine
│   │   └── scorer.py        # Automated scoring + aggregation
│   ├── frontend/
│   │   └── app.py           # NiceGUI pages (Inbox, Wiki, Graph, Query, Digest)
│   └── api/
│       ├── routes_ingest.py     # POST /ingest, /ingest/file, /ingest/url
│       ├── routes_query.py      # POST /query
│       ├── routes_graph.py      # POST /graph/query-as-of, /graph/entity, /graph/export
│       ├── routes_community.py  # POST /community/build, GET /community/clusters
│       └── routes_surfacing.py  # POST /surfing/contradictions, /surfing/digest
├── tests/                   # 145+ unit & integration tests (pytest)
├── data/
│   ├── sample_vault/        # Sample Obsidian notes for testing
│   └── eval_results.json    # Latest eval results
├── second-brain/            # Wiki content (cross-linked articles)
└── pyproject.toml
```

## Running Tests

```bash
# All fast tests (~11s)
pytest tests/ -v --ignore=tests/test_hybrid_3way.py --ignore=tests/test_pipeline_graph.py

# Full suite (includes model loading)
pytest tests/ -v
```

## Evaluation Results

The eval harness tests 15 golden queries across 4 types:

| Query Type | Accuracy | Count |
|-----------|----------|-------|
| Single-hop | 100% | 4 |
| Multi-hop | 65.3% | 3 |
| Point-in-time | 75% | 4 |
| Contradiction | 100% | 2 |
| Episodic | 100% | 2 |
| **Overall** | **86.4%** | **15** |

Run the eval:
```bash
python -c "from backend.eval.runner import run_eval, EvalConfig; run_eval(EvalConfig(), verbose=True)"
```

## Three-Tier Memory Model

### Episodic Memory (ChromaDB)
Raw captures — immutable, timestamped, vector-indexed. Every note, PDF page, or web clip becomes an episodic chunk with dense embeddings for semantic search.

### Semantic Memory (NetworkX Bi-Temporal Graph)
Entities + facts + relations, each with bi-temporal validity windows. New facts supersede old ones without deleting history. Enables point-in-time queries and contradiction detection.

### Community Memory (Topic Clusters)
Facts are clustered by embedding similarity into topic groups, each with an LLM-generated summary. Enables topic-level queries and digest generation.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ingest` | Ingest a local file/directory |
| POST | `/ingest/file` | Ingest an uploaded file |
| POST | `/ingest/url` | Ingest a URL/browser clip |
| POST | `/query` | Hybrid search (dense + BM25 + graph) |
| POST | `/graph/query-as-of` | Facts valid as of a date |
| POST | `/graph/entity` | Entity neighborhood traversal |
| POST | `/graph/contradictions` | Find contradictions |
| POST | `/graph/extract` | On-demand LLM extraction |
| GET | `/graph/export` | Cytoscape.js graph export |
| GET | `/graph/stats` | Graph statistics |
| GET | `/graph/entities` | List all entities |
| POST | `/community/build` | Cluster facts into topics |
| GET | `/community/clusters` | List topic clusters |
| POST | `/community/search` | Search clusters by query |
| POST | `/surfing/contradictions` | Detect contradictions |
| POST | `/surfing/resurface` | Resurface stale notes |
| POST | `/surfing/digest` | Generate digest report |
| POST | `/surfing/run-daily` | Trigger daily job manually |
| GET | `/surfing/scheduler` | Scheduler status |

## Frontend (NiceGUI)

The NiceGUI frontend is mounted at `/ui` on the FastAPI server. Pages:

- **Home** (`/ui/`) — Dashboard with quick links
- **Inbox** (`/ui/ingest`) — Ingest files, view storage stats
- **Wiki** (`/ui/wiki`) — Browse topic clusters and summaries
- **Graph** (`/ui/graph`) — Interactive ECharts graph explorer with filters
- **Query** (`/ui/query`) — Chat-style interface with point-in-time date picker
- **Digest** (`/ui/digest`) — Daily/weekly digests, contradiction reports

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
- **Three-tier memory** — episodic (raw), semantic (facts), community (topics) mirrors human memory
- **NiceGUI over React** — pure Python, no JS build pipeline, runs on the same server
- **APScheduler for surfacing** — simple cron jobs, no Celery/Redis complexity

## License

MIT
