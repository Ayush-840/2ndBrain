# Hybrid Retrieval: Combining Graph, Vector, and Keyword Search

No single retrieval method handles every query well. The strongest systems combine three approaches and blend their scores.

## The Three Methods

- **Graph retrieval** — Follow relationships in a knowledge graph. Best for "how do A and B relate?" questions. Requires structured links between concepts. See [[graph-rag]] for how this works.
- **Vector retrieval (semantic search)** — Embed documents, find nearest neighbors in embedding space. Best for fuzzy, meaning-based queries. Requires an embedding model and vector store.
- **BM25 (keyword search)** — Classic term frequency matching. Best for exact matches, proper nouns, specific phrases. No model needed.

## Why Hybrid Wins

- Graph handles structural queries (relationships, hierarchies)
- Vectors handle semantic queries (paraphrases, abstract concepts)
- BM25 handles exact queries (names, acronyms, specific terms)
- Blending scores covers the gaps each method has alone

## Score Fusion Strategies

- **Linear combination** — Weighted sum of normalized scores from each method
- **Reciprocal Rank Fusion (RRF)** — Combine rankings, not scores. More robust to scale differences between methods.
- **Learning to rank** — Train a model on which combination works best for your data.

## When to Use What

| Query type | Best method | Example |
|------------|-------------|---------|
| Relationship | Graph | "How do local-first and RAG connect?" |
| Semantic | Vector | "What are the downsides of cloud storage?" |
| Exact | BM25 | "What is Karpathy's LLM-wiki method?" |
| Mixed | Hybrid | "What approaches exist for knowledge retrieval?" |

This vault uses [[karpathy-pattern]] (index routing) as a lightweight alternative to vectors. When the vault gets dense enough, add vectors on top.

## Key Takeaways

- No single retrieval method is best for all queries
- Graph, vector, and BM25 each cover different query types
- Hybrid systems blend scores to handle the widest range
- Reciprocal Rank Fusion is the most robust fusion strategy
- Start simple (one method), add complexity when queries demand it
