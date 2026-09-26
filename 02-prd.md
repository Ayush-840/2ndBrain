# PRD — 2ndBrain: WhatsApp Capture & Usage-Context Memory (Phase 6 & 7)

**Product:** 2ndBrain (existing repo: Ayush-840/2ndBrain)
**This document covers:** the extension that adds "share it to yourself on WhatsApp, and the system remembers what it's for"
**Owner:** you (single-user personal system)
**Status:** Draft for build

---

## 1. Vision

> Every important document I send myself on WhatsApp should land in my second brain automatically, tagged with *what it is, why I saved it, and when I'll need it* — so months later I can ask "where's that document for X" and get the actual file and the actual context back, not just a text snippet.

## 2. Problem Statement

Today, important documents live in WhatsApp "Message Yourself," scattered and unsearchable beyond WhatsApp's own basic search. 2ndBrain can already ingest markdown and PDFs *if they're placed in a vault folder*, which does not match how documents actually arrive. There is also no field anywhere in the system for *why* a document matters or *where it will be used* — everything is treated as "content to embed," when for documents the purpose is often the most important piece of metadata.

## 3. Goals

- **G1.** Any document (PDF, image, or text) sent to a dedicated WhatsApp number reaches the 2ndBrain store automatically, within seconds, no manual upload step.
- **G2.** Every ingested document gets a **usage-context**: a short human/AI-generated description of what it's for and when it matters, editable by the user.
- **G3.** The user can ask natural-language questions like *"which file do I need for my visa renewal"* and get the right document back, not just semantically similar text.
- **G4.** The system can proactively remind the user via WhatsApp when a document's relevance window is approaching (e.g., renewal, expiry, deadline).
- **G5.** All of this is added without breaking or slowing down the existing markdown/PDF vault ingestion pipeline.

### Non-Goals (explicitly out of scope for this phase)

- Full life-logging (health data, financial account aggregation, location history).
- Multi-user / shared-household support — this is a single-user, single-tenant system.
- Replacing WhatsApp as a messaging app, or sending outbound messages to anyone other than the owner.
- A polished mobile app — the WhatsApp chat itself *is* the mobile capture UI; the NiceGUI frontend remains desktop/browser-oriented.

## 4. Persona

**"You" — the only user.** Technically comfortable, already runs the FastAPI/NiceGUI stack locally, wants a system they fully understand rather than a black-box SaaS. Primary devices: phone (WhatsApp) for capture, laptop (browser) for deep search/graph exploration.

## 5. User Stories

| ID | As the user, I want to... | So that... |
|---|---|---|
| US-1 | Forward or send any document to my "brain" WhatsApp number | it's captured without opening a laptop |
| US-2 | Add a one-line caption when I send it (e.g., "for tax filing") | the system knows the purpose right away |
| US-3 | Get a WhatsApp reply confirming what was captured and its inferred purpose | I can correct it immediately if wrong |
| US-4 | Ask the system later, in plain language, which document I need for a task | I don't have to remember file names or dates |
| US-5 | Get a nudge before a document becomes stale or urgent (renewal, deadline) | nothing important slips past me |
| US-6 | See all "documents" (not just notes) as their own browsable category in the UI | documents don't get lost among note chunks |
| US-7 | Trust that sensitive documents (ID, financial, medical) are stored securely | I'm comfortable putting real personal data in |

## 6. Features & Priority

### P0 — Must ship first

| Feature | Description |
|---|---|
| **WhatsApp inbound capture** | Webhook receives documents/images sent to a dedicated WhatsApp Business (Cloud API) test number; downloads media; creates a `Capture` exactly like the existing markdown/PDF adapters do. |
| **Caption-aware purpose extraction** | If a caption is present, it's passed to the Claude extractor alongside the document's own text/OCR content to infer `usage_context`, `purpose_tags`, and (if applicable) `valid_until`. |
| **Confirmation reply** | Within a few seconds, the system replies on WhatsApp with a one-line summary of what was captured and its inferred purpose, plus a simple way to correct it ("reply 'no, it's actually for X'"). |
| **`Document` entity in the graph** | New node type alongside existing `Fact` nodes, carrying `usage_context`, `purpose_tags`, `source_channel`, `valid_until` (nullable), linked to its episodic chunk(s). |
| **Basic security hardening** | Replace default `admin`/`changeme`, require a real password/secret on first run, encrypt the document blob store at rest, restrict the webhook to verified requests from Meta + allow-listed sender number only. |

### P1 — Next

| Feature | Description |
|---|---|
| **Documents view in NiceGUI** | New `/ui/documents` page: browse by purpose tag, search, see validity/expiry status at a glance (green/amber/red). |
| **Proactive resurfacing via WhatsApp** | Extend the existing `surfacing/agent.py` daily job to also push a WhatsApp message when a document's `valid_until` is within N days, or when a contradiction/duplicate is detected. |
| **Purpose-aware retrieval boost** | When a query resembles "which document / file / form do I need for X," bias hybrid retrieval toward `Document` nodes whose `purpose_tags` match, not just semantic similarity of raw text. |
| **Manual correction flow** | A WhatsApp reply like "that's actually for my rent, not tax" updates the `usage_context` in place (with the same bi-temporal supersede pattern the graph already uses for facts). |

### P2 — Later

| Feature | Description |
|---|---|
| **Voice note capture** | Transcribe WhatsApp voice notes into episodic captures (quick verbal reminders, not just documents). |
| **Email-forward capture** | A dedicated inbox address as a second capture channel for documents that arrive by email rather than WhatsApp. |
| **Browser clipper** | Revive the "browser clip" capture path already named in the architecture diagram but not yet built. |
| **Life-area taxonomy** | A small fixed set of top-level tags (Work / Health / Finance / Family / Learning / Admin) surfaced across search, digest, and graph views. |

## 7. Success Metrics

- **Capture latency:** median time from "document sent on WhatsApp" to "confirmation reply received" < 15 seconds.
- **Purpose-extraction accuracy:** ≥ 80% of auto-inferred `usage_context` values accepted without correction (measured by how often the user replies with a correction).
- **Retrieval quality:** new "usage-context recall" eval category (see Research Paper §7) scores ≥ 80%, in line with the existing single-hop/contradiction categories.
- **Zero unintended exposure:** no default credentials left active in any environment where the webhook is publicly reachable.

## 8. Release Plan

| Milestone | Scope |
|---|---|
| **6.0** | WhatsApp webhook receiver + media download + plain ingestion (no purpose extraction yet) — proves the pipe works end to end. |
| **6.1** | Purpose extraction + confirmation reply + `Document` graph node. |
| **6.2** | Security hardening (auth, encryption, allow-list) — **gate before any real personal documents are sent through it.** |
| **7.0** | Documents UI page + purpose-aware retrieval boost. |
| **7.1** | Proactive WhatsApp resurfacing/reminders. |
| **8.0** (stretch) | Voice notes, email capture, browser clipper, life-area taxonomy. |

## 9. Risks & Assumptions

- Assumes Meta's free developer/test-number tier remains available for a single allow-listed personal recipient (see TRD for the exact setup and its limits).
- Assumes the user is comfortable running a small always-on process (or a lightweight VPS) to host the webhook, since WhatsApp requires a publicly reachable HTTPS endpoint.
- LLM purpose-extraction will not be perfect on day one; the correction loop (US-3) is the mitigation, not a claim of perfect accuracy.

## 10. Open Questions

1. Should expired documents (past `valid_until`) be archived out of default search results, or just visually flagged? (Recommendation: flagged, never hidden — bi-temporal philosophy says never delete/hide history silently.)
2. Single WhatsApp number for everything, or a separate "quick capture" vs "important document" distinction? (Recommendation: start with one number; let captions/purpose tags do the sorting rather than multiple numbers.)
