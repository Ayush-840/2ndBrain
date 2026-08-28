# How Local-First, Graph RAG, and AI Agents Relate

These three concepts form a stack — each layer enables the one above it:

```
┌─────────────────────────────────────┐
│         AI AGENTS                   │  ← the worker (ingest, synthesize, maintain)
│   Librarian pattern: one role,      │
│   one territory, one spec           │
├─────────────────────────────────────┤
│         GRAPH RAG                   │  ← the routing layer (how to find knowledge)
│   Index → topic → article           │
│   Relationships over similarity     │
├─────────────────────────────────────┤
│       LOCAL-FIRST SOFTWARE          │  ← the foundation (where knowledge lives)
│   Plain text on disk                │
│   No lock-in, no infrastructure     │
└─────────────────────────────────────┘
```

## The Connections

**[[local-first-software]] → [[ai-agents]]:** Plain text files are the simplest interface an agent can work with. No API, no sync layer, no proprietary format. The agent reads and writes markdown directly. You can debug exactly what it did. Swap the LLM, keep the knowledge base.

**[[local-first-software]] → [[graph-rag]]:** Markdown files with `[[wiki links]]` create a graph implicitly. Every cross-link is an edge. No vector DB needed — the file system *is* the graph. The [[karpathy-pattern]] (index → topic → article) works because files are just text on disk.

**[[graph-rag]] → [[ai-agents]]:** The agent needs to retrieve context before it can synthesize. Graph RAG gives it structured routing: read the master index, pick a topic, read the topic index, read 1-3 articles. Three or four targeted reads per query instead of scanning everything.

**[[ai-agents]] → [[graph-rag]]:** The agent maintains the graph. It creates topics, writes articles, updates indexes, adds cross-links. Without the agent, the graph decays. Without the graph, the agent can't find anything.

## The Flywheel

```
Drop files in raw/
    ↓
Agent reads (graph RAG routes)
    ↓
Agent writes wiki articles + cross-links
    ↓
Graph grows denser
    ↓
Next query has more context
    ↓
Synthesis gets better
    ↓
Repeat
```

Each cycle compounds. The wiki gets denser every day — while you sleep, travel, work, live. See [[compound-knowledge]] for the full theory of how this flywheel accelerates.

## Key Takeaways

- Local-first is the foundation — plain text on disk, no infrastructure
- Graph RAG is the routing layer — index → topic → article, relationships over similarity
- AI agents are the worker — ingest, synthesize, maintain the graph
- Each layer enables the one above it
- The flywheel: every compile makes the next query smarter
