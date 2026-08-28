# Graph RAG: Structured Retrieval for Knowledge Bases

Retrieval-Augmented Generation (RAG) is the standard pattern: embed documents, find similar chunks, feed them to an LLM. But naive RAG has a blind spot — it retrieves by similarity, not by relationship. Graph RAG fixes this.

## The Problem With Vector-Only RAG

- Embeddings capture semantic similarity, not structure
- No awareness of how concepts connect
- Synthesis questions ("how do A and B relate?") get weak answers
- You end up reading 10 chunks when 2 targeted reads would do

## How Graph RAG Works

- Build a knowledge graph alongside your vector index
- Nodes = concepts, entities, topics
- Edges = relationships, references, cross-links
- At query time: follow the graph to find relevant nodes, then retrieve only the chunks attached to those nodes

## The Karpathy Pattern

Andrej Karpathy's LLM-wiki method uses a simple hierarchy:
1. Master index → routes to topics
2. Topic index → routes to articles
3. Articles → contain the actual content

No embeddings, no vector DB. Three or four targeted reads per query. Scales to thousands of documents. See [[karpathy-pattern]] for the full pattern.

## Hybrid: Best of Both

The strongest approach combines graph + vectors:
- Graph for routing and relationship queries
- Vectors for fuzzy semantic search
- BM25 for exact keyword matching
- Hybrid retrieval blends all three scores

See [[hybrid-retrieval]] for fusion strategies and when to use each method.

## How This Vault Uses It

- `[[wiki links]]` create a graph implicitly — every cross-link is an edge
- `_master-index.md` → topic `_index.md` → articles is the routing hierarchy
- [[ai-agents]] (the librarian pattern) maintains the graph
- [[local-first-software]] provides the plain-text storage layer

## Key Takeaways

- Vector RAG retrieves by similarity; Graph RAG retrieves by relationship
- A knowledge graph adds structure that embeddings miss
- The Karpathy pattern (index → topic → article) is a simple graph without infrastructure
- Hybrid retrieval (graph + vector + BM25) handles the widest range of queries
- Cross-linking your notes creates a graph implicitly — every [[wiki link]] is an edge
