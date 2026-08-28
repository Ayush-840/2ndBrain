# Weekly Audit — 2026-08-28

## Summary

- **Topics:** 2
- **Articles:** 1
- **Wiki links found:** 6
- **Broken links:** 1
- **Missing articles:** 1
- **Inconsistencies:** 0

---

## 🔴 Broken Link

| Link | Where | Issue |
|------|-------|-------|
| `[[why-local-first-matters]]` | `local-first-software/_index.md` | Points to article that doesn't exist in wiki. Raw file exists at `raw/2026-08-28-why-local-first-matters.md` but was never compiled. |

**Fix:** Compile `raw/2026-08-28-why-local-first-matters.md` into `wiki/local-first-software/why-local-first-matters.md`.

---

## 🟡 Missing Article (referenced but unwritten)

| Reference | Where | Notes |
|-----------|-------|-------|
| `[[why-local-first-matters]]` | `local-first-software/_index.md` | Topic index references this article but it hasn't been created yet |

---

## ✅ Healthy Links

| Link | From | Resolves To |
|------|------|-------------|
| `[[local-first-software]]` | `_master-index.md` | `wiki/local-first-software/` ✓ |
| `[[graph-rag]]` | `_master-index.md` | `wiki/graph-rag/` ✓ |
| `[[graph-rag-explained]]` | `graph-rag/_index.md` | `wiki/graph-rag/graph-rag-explained.md` ✓ |
| `[[local-first-software]]` | `graph-rag/_index.md` | `wiki/local-first-software/` ✓ |
| `[[local-first-software]]` | `graph-rag-explained.md` | `wiki/local-first-software/` ✓ |

---

## 🟡 Suggested New Topics

Based on content in existing articles:

| Topic | Why |
|-------|-----|
| **hybrid-retrieval** | `graph-rag-explained.md` discusses hybrid (graph + vector + BM25) — could be its own topic with deeper coverage |
| **karpathy-pattern** | Referenced in graph-rag — the LLM-wiki method is a distinct pattern worth its own article |

---

## 📋 Focus List for Next Week

1. **[High]** Compile `raw/2026-08-28-why-local-first-matters.md` → fix broken link
2. **[Low]** Consider expanding hybrid-retrieval and karpathy-pattern into their own topics
3. **[Low]** Add `graph-rag-explained.md` back-link to `local-first-software/_index.md` (currently one-directional)
