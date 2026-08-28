# Graph RAG: Structured Retrieval for Knowledge Bases

Retrieval that follows relationships, not just similarity.

## The Core Idea

Traditional RAG embeds documents and finds nearest neighbors. Graph RAG adds structure:
- Nodes = concepts, entities, topics
- Edges = relationships, references, cross-links
- Query time: follow the graph to relevant nodes, then retrieve attached content

## Three Levels of Graph RAG

| Level | Implementation | Infrastructure |
|-------|---------------|----------------|
| **Lightweight** | `[[wiki links]]` in markdown | None — file system is the graph |
| **Medium** | Index → topic → article hierarchy | Just markdown files |
| **Full** | Explicit knowledge graph + vector store | Graph DB + embedding model |

This vault uses the lightweight level. See [[karpathy-pattern]] for the medium level.

## Why Graph Beats Vector-Only

- Vector RAG retrieves by **similarity** — "find text that looks like this"
- Graph RAG retrieves by **relationship** — "find text connected to this"
- Synthesis questions ("how do A and B relate?") need relationships, not similarity
- Cross-linking your notes creates a graph implicitly — every `[[wiki link]]` is an edge

## Hybrid: Best of Both

The strongest systems combine graph + vector + BM25:
- Graph for routing and relationship queries
- Vectors for fuzzy semantic search
- BM25 for exact keyword matching

See [[hybrid-retrieval]] for fusion strategies.

## How This Vault Uses It

- `[[wiki links]]` between articles create edges
- `_master-index.md` → topic `_index.md` → articles is the routing hierarchy
- [[ai-agents]] maintains the graph (creates topics, writes articles, adds cross-links)
- [[local-first-software]] provides plain-text storage

## Key Takeaways

- Graph RAG retrieves by relationship, not just similarity
- `[[wiki links]]` create a graph implicitly — every cross-link is an edge
- Three levels: lightweight (markdown links) → medium (index hierarchy) → full (graph DB)
- Hybrid retrieval (graph + vector + BM25) handles the widest range of queries
- Cross-linking is the cheapest graph — no infrastructure required

See [[graph-rag-explained]] for the full technical breakdown.
