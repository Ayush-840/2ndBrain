# PRD — Personal AI Second Brain

**Based on:** your uploaded research paper ("Comprehensive Architecture and Design for a Personal AI 'Second Brain' System") + `06-additional-features.md`
**Frontend:** React (Next.js) — per your request
**User:** single-tenant, personal use

---

## 1. Vision

> One private system that holds everything about me — my identity, my documents, my family, my goals, my history — and answers questions about any of it in plain language, as reliably as asking a person who has perfect memory of my life.

## 2. Problem Statement

Personal information today is split across three incompatible places: physical/scanned documents (passport, mark sheets, contracts), scattered notes about people and goals, and the user's own memory of *why* something matters and *when* it's relevant again. None of these are searchable together, none are time-aware (old facts get silently overwritten), and nothing proactively tells the user when something needs attention (a renewal, a goal deadline, a contradiction between a document and what's on record).

## 3. Goals

- **G1.** Structured personal facts (identity, family, education, goals, timeline) are queryable instantly and precisely — no LLM roundtrip needed for "what's my current address."
- **G2.** Any document — PDF, photo, scan — is ingested, categorized, summarized, and made semantically searchable, arriving via upload **or** WhatsApp/email, not just a file picker.
- **G3.** The system detects when a new document contradicts or updates a known fact (e.g., new mark sheet vs. recorded GPA) and asks for confirmation instead of silently trusting either source.
- **G4.** Nothing important is forgotten passively — expiries, renewals, and goal deadlines generate proactive reminders.
- **G5.** The most sensitive data (identity documents, financial, medical) is protected by field-level encryption and, by default, answered only by a local LLM.
- **G6.** The frontend is a modern React (Next.js) application: fast, installable as a PWA, with a command-palette-driven capture/search flow.

### Non-Goals

- Multi-user/family-shared accounts (single-tenant only, for now — sharing is a stretch goal, not P0).
- Replacing a full EHR/medical record system or a bank's own financial software — the system stores and surfaces documents/summaries about these domains, not transacts within them.
- Building a fully offline mobile app — the target is a responsive/installable web app (PWA), not a native iOS/Android build.

## 4. Persona

**"You."** The sole user and administrator. Wants a private system they control end-to-end (local-first, self-hosted), comfortable running a small stack, and wants the assistant to feel like *talking to someone who knows their whole life*, not filling out another database form.

## 5. User Stories

| ID | As the user, I want to... | So that... |
|---|---|---|
| US-1 | Ask "which college am I attending" and get an instant, exact answer | I don't wait on an LLM for facts that are already structured |
| US-2 | Upload or WhatsApp a document and have it auto-categorized and summarized | I never have to manually tag or file anything |
| US-3 | Be told when a new document conflicts with what's on record | my profile never silently drifts out of sync with reality |
| US-4 | Get reminded before my passport/visa/insurance expires | nothing important lapses without warning |
| US-5 | See my whole life — documents, goals, milestones — as one timeline | I get a sense of the whole picture, not fragments |
| US-6 | See my family/contacts as a graph, not a flat list | relationships between people are visible, not just names |
| US-7 | Trust that identity/medical/financial data never leaves my machine | I feel safe storing my most sensitive information here |
| US-8 | Use a fast command-palette (`Cmd+K`) to capture a thought or search from anywhere | capture friction is near zero |
| US-9 | Install the app on my phone home screen | it feels like a real app, not just a browser tab |

## 6. Features & Priority

### P0 — Foundation (must ship first)

| Feature | Notes |
|---|---|
| Personal Profile Engine (identity, family, education, goals, timeline) | Directly from research paper §2.1/§4.1 — structured relational schema, instant SQL-backed answers. |
| Document ingestion pipeline (upload → OCR/extract → LLM metadata → embed) | Research paper §4.2, PDF/PNG/JPG/DOCX/TXT. |
| Hybrid Query Engine (intent classifier → SQL / vector / hybrid) | Research paper §5. |
| React (Next.js) dashboard: profile view, document vault, chat interface | See TRD for full page/component list. |
| WebAuthn (passkey) login, PIN fallback | Research paper §7.3, hardened per feature extensions §4. |
| At-rest encryption (volume-level AES-256) + field-level encryption for identity/financial columns | Research paper §7.2 + extensions §4. |

### P1 — Next

| Feature | Notes |
|---|---|
| Bi-temporal history on profile/goals tables | Extensions §1. |
| WhatsApp + email-forward capture channels | Extensions §2. |
| Document expiry/renewal tracking + reminder engine | Extensions §1/§2. |
| Contradiction detection on new document ingest | Extensions §2. |
| Life dashboard (chronological timeline view) | Extensions §1. |
| Relationship graph view (family/contacts) | Extensions §1/§5. |
| Command palette (`Cmd+K`) | Extensions §5. |
| Full audit log | Extensions §4. |

### P2 — Later

| Feature | Notes |
|---|---|
| Privacy-tiered LLM routing (local vs. cloud by sensitivity) | Extensions §3. |
| Proactive daily/weekly digest | Extensions §3. |
| Voice query in/out | Extensions §3. |
| Calendar sync | Extensions §6. |
| Data export/portability | Extensions §4. |
| Installable PWA polish, document-viewer inline highlight | Extensions §5. |

## 7. Success Metrics

- **Structured query latency:** < 1 second for direct profile/DB lookups (research paper NFR).
- **RAG query latency:** < 3 seconds end-to-end for document/semantic queries (research paper NFR).
- **Categorization accuracy:** ≥ 85% of ingested documents correctly auto-categorized without manual correction.
- **Contradiction recall:** ≥ 90% of introduced test contradictions (e.g., mismatched GPA) correctly flagged.
- **Zero plaintext exposure:** field-level encryption verified on every column tagged "high sensitivity" before go-live.

## 8. Release Plan

Mirrors and extends the research paper's own roadmap (§8):

| Phase | Scope |
|---|---|
| **1. Foundation** | FastAPI backend, Postgres schema (profile/family/goals/timeline), Next.js shell + auth (WebAuthn). |
| **2. Document Engine** | Upload pipeline, OCR, LLM metadata extraction, ChromaDB/Qdrant indexing, document vault UI. |
| **3. Hybrid Retrieval & RAG** | Intent classifier, SQL + vector + hybrid paths, chat interface with source citations. |
| **4. Dashboard & Testing** | Full React dashboard, document viewer, end-to-end eval + benchmarks. |
| **5. Time & Proactivity** *(new)* | Bi-temporal history, expiry/reminder engine, contradiction detection, life-timeline view. |
| **6. Multi-channel Capture** *(new)* | WhatsApp + email ingestion adapters, relationship graph view, command palette. |
| **7. Privacy Maturity & Extras** *(new)* | Privacy-tiered LLM routing, audit log, data export, voice I/O, calendar sync. |

## 9. Risks & Assumptions

- Local LLM (Ollama) quality/latency trade-off must be validated for the "always local for sensitive categories" policy to be acceptable in practice — a fallback plan (smaller local model, or explicit user override with warning) should exist if local-only responses are too weak for complex documents.
- OCR accuracy on poor-quality scans/photos will require the confidence-tiering + human-confirmation loop (extensions §2) from day one, not as an afterthought.
- Single-tenant assumption simplifies auth/access-control significantly; revisit if sharing is ever added.

## 10. Open Questions

1. Should contradiction detection auto-update the profile after confirmation, or always require an explicit "accept" click? (Recommendation: always explicit — never silently mutate structured facts.)
2. Where should the line sit between "Personal Memory" structured fields and "Document" free-form facts — e.g., is a GPA a profile field, a document-derived fact, or both, kept in sync? (Recommendation: profile field is the source of truth for display; documents can *propose* updates via the contradiction-detection flow, never write directly.)
