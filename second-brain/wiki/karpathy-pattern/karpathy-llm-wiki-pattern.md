# Karpathy's LLM-Wiki Pattern

Andrej Karpathy proposed a simple knowledge management pattern: use a hierarchical index structure to route LLM queries, avoiding vector databases entirely.

## The Core Idea

Instead of embedding everything and doing similarity search, use a human-readable index hierarchy:

1. Master index → lists all topics with one-line summaries
2. Topic index → lists all articles in that topic
3. Articles → contain the actual knowledge

## How Queries Work

The LLM reads the master index, picks the relevant topic, reads that topic's index, picks the relevant articles, and synthesizes from there. Three or four file reads per query.

## Why It Works

- **No infrastructure** — Just markdown files on disk
- **No embeddings** — The LLM does the routing with its own reasoning
- **No vector DB** — No external service to manage or pay for
- **Scales to thousands** — Indexes stay small even as article count grows
- **Debuggable** — You can read the indexes yourself and see exactly how routing works

This relies on [[local-first-software]]: plain text files on disk are the simplest possible interface.

## The Tradeoff

- Requires well-maintained indexes (someone has to keep them current)
- Not as flexible as semantic search for fuzzy queries
- Routing quality depends on index quality
- Works best with clear topic boundaries

See [[hybrid-retrieval]] for when to add vectors on top of this pattern.

## How This Vault Uses It

This vault is a direct implementation:
- `_master-index.md` routes to topics
- Each topic has `_index.md` listing articles
- Articles contain the knowledge
- [[ai-agents]] (the librarian pattern) executes the workflow

## Key Takeaways

- Karpathy's pattern: master index → topic index → articles (three reads per query)
- No vector DB, no embeddings, no infrastructure — just markdown files
- The LLM does the routing using its own reasoning over indexes
- Works best when topics have clear boundaries and indexes are maintained
- This vault is a direct implementation of this pattern
