# UI Design — Simple, NiceGUI-Native (No New Framework)

Design principle carried over from the repo's own stated choice: **"NiceGUI over React — pure Python, no JS build pipeline."** The additions below follow that same rule: plain NiceGUI components, reusing the existing page layout/nav pattern (`Home / Inbox / Wiki / Graph / Query / Digest`), just adding one page and a small addition to the Inbox page.

---

## 1. Updated navigation

```
┌─────────────────────────────────────────────────────────────┐
│  2ndBrain     Home  Inbox  Documents ⭐  Wiki  Graph  Query  Digest │
└─────────────────────────────────────────────────────────────┘
```

Only one new top-level tab: **Documents**. Everything else stays where it is.

## 2. Inbox page (`/ui/ingest`) — small addition

Existing page already shows storage stats and lets you ingest files. Add a "Capture Sources" status strip at the top:

```
┌─────────────────────────────────────────────────────────────┐
│  Capture Sources                                             │
│  ● Vault folder        watching data/sample_vault            │
│  ● WhatsApp            connected · last capture 4 min ago    │
└─────────────────────────────────────────────────────────────┘
```

Green dot = healthy / recently active. Amber = configured but no signature verified in >24h (possible webhook issue worth checking). Red = not configured. This is just a status readout of what `config.py` and the last few processed messages already tell the backend — no new data collection needed.

## 3. New page: `/ui/documents`

This is the home for anything captured as a `DocumentNode` (WhatsApp documents/images, plus any PDF ingested the old way). Notes/facts continue to live in Wiki/Graph as today; Documents is specifically for "files with a purpose."

```
┌─────────────────────────────────────────────────────────────┐
│  Documents                                    [ Search... ]  │
│                                                                │
│  Filter:  [All] [Tax] [Finance] [Health] [Admin] [Other]      │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 📄 rental_agreement.pdf                                │    │
│  │    "For tax filing, needed every March"                │    │
│  │    via WhatsApp · captured Sep 12, 2026                │    │
│  │    ⏰ relevant again: Mar 2027                          │    │
│  │                                          [Edit purpose]│    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 📄 visa_approval.pdf                                    │    │
│  │    "Visa document, renew before expiry"                │    │
│  │    via WhatsApp · captured Aug 30, 2026                │    │
│  │    🔴 expires in 12 days                                │    │
│  │                                          [Edit purpose]│    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

- **Card layout**, not a table — each document is a self-contained unit with icon, filename, the human-readable `usage_context`, source, capture date, and a status chip for `valid_until` (🟢 not time-sensitive / 🟡 approaching / 🔴 expiring soon).
- **[Edit purpose]** opens an inline text field — editing here uses the exact same "supersede, don't overwrite" backend call the WhatsApp correction-reply flow uses, so both paths stay consistent.
- **Filter chips** are just the `purpose_tags` used elsewhere in the system (Tax / Finance / Health / Admin / Other) — same taxonomy everywhere, not a separate tagging system for this one page.

## 4. Digest page (`/ui/digest`) — small addition

Add one new section alongside the existing daily/weekly digest and contradiction report:

```
┌─────────────────────────────────────────────────────────────┐
│  Documents needing attention                                  │
│  🔴 visa_approval.pdf — expires in 12 days                    │
│  🟡 insurance_card.pdf — renews in 25 days                    │
└─────────────────────────────────────────────────────────────┘
```

This mirrors exactly what gets pushed proactively over WhatsApp per the TRD's resurfacing extension — the WhatsApp message and this dashboard section are two views of the same underlying `/documents/expiring` query, so they never disagree with each other.

## 5. What we deliberately did NOT add

- No new design system, no React, no charting library — reusing NiceGUI's existing card/table primitives already used by the Wiki and Graph pages.
- No separate "WhatsApp inbox" chat-replica UI — the actual WhatsApp app is the capture UI; the web UI only shows the *result* of captures, avoiding building a second messaging interface nobody asked for.
- No bulk-upload dropzone redesign — the existing Inbox page's ingestion UI is left as-is; only the status strip is added.

This keeps the surface area of the frontend change small: one new page, two small additions to existing pages, zero new dependencies.
