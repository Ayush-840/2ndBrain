# Feature Extensions — Personal AI Second Brain

Builds directly on your research paper's 3-tier architecture (Personal Memory Module, Document Ingestion Engine, Intelligence Layer). Nothing below replaces what's already designed — each item is an addition to a named section of the original paper, with a short reason it earns its place in a *personal* system rather than being generic feature bloat.

---

## 1. Personal Memory Module — additions

| Feature | Extends | Why |
|---|---|---|
| **Bi-temporal history on every profile field** | `user_profile`, `personal_goals` | Right now an `UPDATE` to `current_address` or `degree_pursuing` silently loses the old value. Add `valid_from` / `valid_to` to every mutable table (same pattern used in temporal-graph personal-AI systems like Graphiti) so "what was my address before I moved" is answerable, not overwritten. |
| **Relationship graph, not just a table** | `family_members` | A table answers "who is my sister"; a graph answers "who introduced me to my landlord" or "which of my contacts work at the same company." Model relations as edges (`person_a`, `relation_type`, `person_b`) so it's traversable, not just listable. |
| **Recurring reminder engine** | `personal_goals`, `timeline_events` | Goals have a `target_date` but nothing acts on it. Add a scheduler that converts target dates, document expiries, and birthdays in `family_members` into a unified reminder feed. |
| **Goal check-ins** | `personal_goals` | A `status` field alone can't show progress over time. Add lightweight periodic check-ins (`% complete`, short note) so goal history is itself a timeline, not a single mutable flag. |
| **Life dashboard / timeline feed** | `timeline_events` | Surface `timeline_events` + document key-dates + goal check-ins as one chronological feed — this is the single view that makes "second brain" feel alive rather than a form you filled in once. |

## 2. Document Engine — additions

| Feature | Extends | Why |
|---|---|---|
| **Multi-channel capture** | Section 4.2 ingestion pipeline | The paper assumes a file-upload interface. In practice, most important documents arrive via WhatsApp ("message yourself"), email attachments, or a phone camera. Add adapters for: WhatsApp Cloud API webhook, an email-forward inbox address, and a mobile camera "scan to PDF" capture — all converging on the *same* ingestion pipeline (extraction → metadata → embedding) the paper already defines. |
| **Document expiry & renewal tracking** | `documents` table | Add `key_dates JSONB` (e.g., `{"expires_on": "2027-03-01", "renew_by": "2027-01-15"}`), extracted automatically by the same LLM metadata step that already produces `document_type`/`tags`. Feeds directly into the reminder engine above — a passport or insurance card should nudge you before it lapses. |
| **Version & contradiction detection** | Section 5, hybrid query example | The paper's own example — *"does my uploaded mark sheet match my current GPA"* — is currently answered only on-demand. Make it proactive: whenever a new document is ingested, automatically diff its extracted facts against the structured profile and flag mismatches, instead of waiting for the user to ask. |
| **Confidence-scored auto-categorization** | Section 4.2 step 3 | LLM metadata extraction should return a confidence score alongside `category`/`tags`; anything below a threshold is queued for one-tap human confirmation rather than silently filed wrong. |
| **OCR quality tiering** | OCR service row in tech stack | Use fast local OCR (Tesseract/EasyOCR) as the default pass, and only escalate to a vision-LLM re-read for low-confidence scans (blurry photos, handwriting) — keeps cost and latency down for the common case. |

## 3. Intelligence Layer — additions

| Feature | Extends | Why |
|---|---|---|
| **Privacy-tiered LLM routing** | Section 6, LLM Engine row | Not all queries deserve the same trust boundary. Route by document/category sensitivity: *Identity/Medical/Financial* categories are always answered by the local model (Ollama); general knowledge or non-sensitive documents may use the cloud model for higher quality. This operationalizes the paper's own "Local First" principle instead of leaving it as an all-or-nothing deployment choice. |
| **Conversational session memory** | Section 5, query algorithm | `process_user_query` currently treats each query independently. Add short-term conversation state so follow-ups ("what about the one from last year") resolve against the prior turn, not just the raw query text. |
| **Proactive daily/weekly digest** | New, sits alongside Intelligence Layer | A generated brief: upcoming reminders, newly detected contradictions, goals nearing their target date — pushed to the dashboard and optionally WhatsApp, so the system surfaces things instead of only answering when asked. |
| **Voice query in/out** | New | Speech-to-text for hands-free query entry, and optional text-to-speech for responses — useful specifically for a personal assistant used one-handed on a phone. |

## 4. Security & Privacy — additions

| Feature | Extends | Why |
|---|---|---|
| **Field-level encryption for high-sensitivity columns** | Section 7.2 | Blanket volume-level AES-256 protects against disk theft but not against anyone with DB access. Add column-level encryption (e.g., government ID numbers, bank details) so even a raw DB dump doesn't expose the most sensitive fields in plaintext. |
| **Full access audit log** | Section 7.3 | Every query, document view, and edit gets an append-only log entry (`who/what/when` — trivial for a single-user system, but essential once any sharing feature exists). |
| **Data export / portability** | New | One-click full export (structured data as JSON, documents as original files) — a personal data vault should never be a trap; you should always be able to walk away with everything. |
| **Passkey (WebAuthn) as the default**, PIN as fallback only | Section 7.3 | The paper lists WebAuthn *or* PIN; make WebAuthn the default and PIN a deliberately weaker fallback for low-friction mobile re-entry, not an equal option. |

## 5. Frontend/UX — additions (feeding directly into the React-based PRD/TRD)

- **Command palette** (`Cmd/Ctrl+K`) for instant capture or search from anywhere in the app.
- **Visual timeline** component for the life dashboard (Section 1 above).
- **Force-directed relationship graph** view for family/contacts.
- **Installable PWA** — usable as a phone home-screen app without a native build.
- **Document viewer with inline highlight** — so an answer citing "line item 4" can jump to and highlight that exact spot in the source PDF.

## 6. Integrations — additions

- **Calendar sync** (Google Calendar / ICS export) for reminders and goal target dates.
- **WhatsApp/Telegram bot** as both a capture channel (documents) and a lightweight query channel ("what's my sister's birthday") for on-the-go use without opening the dashboard.
- **Notion/Obsidian one-time import** for anyone migrating existing notes into the system.

These additions are reflected as prioritized, buildable features in the PRD, and as concrete schema/API/architecture changes in the TRD.
