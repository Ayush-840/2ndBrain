# Karpathy Pattern: Index Routing Without Vector Databases

A hierarchical index structure that lets LLMs route queries through markdown files instead of embeddings.

## The Pattern

```
_master-index.md
    ↓ (picks topic)
topic/_index.md
    ↓ (picks article)
topic/article.md
```

Three or four file reads per query. No vector DB, no embeddings, no infrastructure.

## Why It Works

- The LLM does the routing with its own reasoning
- Indexes are human-readable and debuggable
- Plain text files on disk — zero lock-in
- Scales to thousands of documents without degradation

## When to Use It

- **Use when:** Clear topic boundaries, well-maintained indexes, you want simplicity
- **Skip when:** Fuzzy semantic queries, you need similarity search, topics overlap heavily

See [[hybrid-retrieval]] for when to add vectors on top.

## How This Vault Implements It

- `_master-index.md` lists all topics with one-line summaries
- Each topic folder has `_index.md` listing its articles
- Articles contain the actual knowledge
- [[ai-agents]] (the librarian pattern) maintains the indexes

## Related Concepts

- [[local-first-software]] — plain text files make this pattern possible
- [[graph-rag]] — graph retrieval as a more sophisticated alternative
- [[compound-knowledge]] — index routing makes the flywheel fast

## Key Takeaways

- Master index → topic index → articles (three reads per query)
- No infrastructure — just markdown files on disk
- The LLM does the routing, not an embedding model
- Works best with clear topic boundaries
- Add vectors later if queries get fuzzy

See [[karpathy-llm-wiki-pattern]] for the detailed breakdown.
