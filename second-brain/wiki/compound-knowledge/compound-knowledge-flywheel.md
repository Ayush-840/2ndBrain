# Compound Knowledge: The Flywheel Effect

The best knowledge systems don't just store information — they get smarter over time. Every addition makes future additions more valuable. This is the compound effect applied to knowledge.

## Why Knowledge Compounds

- Each new article creates new cross-links to existing articles
- Cross-links reveal connections you wouldn't spot manually
- Synthesis queries pull from a growing corpus, producing richer answers
- Answers get filed back into the wiki, making the next query even better

## The Math of Compounding

With N articles and average K cross-links per article:
- Possible connections: N × (N-1) / 2
- Actual connections grow faster than articles
- A 100-article wiki with 5 links each has 500 edges
- A 1000-article wiki doesn't just 10x — the density increases

## Three Types of Value

- **Storage** — Having the information (baseline)
- **Retrieval** — Finding the right information quickly ([[graph-rag]])
- **Synthesis** — Connecting information to produce new insights ([[ai-agents]])

Storage alone is a library. Storage + retrieval is a search engine. Storage + retrieval + synthesis is a second brain.

## The Maintenance Paradox

The more you add, the more maintenance you need. But the right system flips this:
- Daily ingest automates storage
- Nightly review automates maintenance
- Weekly audit catches what automation misses
- The agent does the work, you make the decisions

See [[ai-agents]] for the librarian pattern that makes this sustainable.

## How This Vault Compounds

1. Drop articles into raw/ (input)
2. Agent compiles them into wiki articles (structure)
3. Cross-links form connections (graph)
4. Queries synthesize across the graph (insight)
5. Synthesis results get filed back (feedback loop)
6. The flywheel spins faster with each cycle

This depends on [[local-first-software]] for the storage layer and [[graph-rag]] for efficient retrieval. See [[karpathy-pattern]] for the index routing that makes queries fast without infrastructure.

## Key Takeaways

- Knowledge compounds when each addition creates new connections
- Synthesis is the multiplier — it turns stored information into new insights
- The maintenance paradox is solved by automation (daily/nightly/weekly)
- Three levels: storage → retrieval → synthesis → compound growth
- The flywheel: every compile makes the next query smarter
