# AI Agents for Knowledge Work

The shift from tools to agents is the biggest change in knowledge work since the spreadsheet. Instead of you operating software, software operates on your behalf — reading, filing, synthesizing, surfacing.

## What Makes an Agent Different From a Tool

- A tool waits for input → produces output (calculator, search engine)
- An agent has a goal → takes actions → observes results → adapts
- The loop is autonomous: plan, act, observe, repeat

## The Three Roles of a Knowledge Agent

- **Ingestion** — Reads raw material, extracts what matters, files it
- **Synthesis** — Connects ideas across documents, generates insights
- **Maintenance** — Keeps the system clean: indexes, links, consistency

## The Librarian Pattern

The simplest effective agent setup: give the agent one clear role (librarian), one clear territory (wiki/), and one clear spec (CLAUDE.md). Don't try to make it do everything. Narrow scope + clear rules > broad capability + vague instructions.

This is exactly how this vault works — see [[local-first-software]] for why the storage layer matters, and [[graph-rag]] for how the agent retrieves context efficiently.

## Why Local-First Enables Better Agents

- Agent can read/write files directly — no API, no sync layer
- Plain text is debuggable — you can see exactly what the agent did
- No vendor lock-in — swap the LLM, keep the knowledge base
- Works offline — the agent runs on your machine, not in the cloud

## Compounding: The Flywheel

Every cycle makes the system smarter:
1. Agent reads raw input
2. Writes structured wiki articles
3. Updates indexes and cross-links
4. Next query has more context to work with
5. Synthesis answers get filed back into the wiki
6. Repeat — the wiki compounds daily

## Key Takeaways

- Agents differ from tools: they loop autonomously (plan → act → observe → repeat)
- The librarian pattern (one role + one territory + one spec) is the simplest effective setup
- Local-first storage makes agents debuggable and portable
- Cross-linking creates emergent knowledge — the graph grows with use
- The flywheel: every compile makes the next query smarter
