# How this vault works

- You're the librarian. The `wiki/` folder is yours to write and maintain. I won't usually edit it directly.
- `raw/` is the inbox. When I drop files there, you process them into the wiki the next time I say "compile."
- `wiki/_master-index.md` is the front door. It lists every topic with a one-line summary. Keep it current.
- Every topic gets its own folder (e.g. `wiki/ai-agents/`) and its own `_index.md` listing the articles in that topic.
- Cross-link everything with `[[wiki links]]`.

## Folder structure

```
second-brain/
├── raw/          # inbox — dump anything, no sorting
├── wiki/         # the AI's territory
│   └── _master-index.md
└── output/       # generated reports
```

## On compile

1. Read the raw file
2. Pick the right topic — or make a new one
3. Write a concise wiki article with key takeaways and links
4. Update the topic's `_index.md` and the master index
5. If a raw file spans multiple topics, split it and cross-link

## House style

- Bullets over paragraphs. Concise.
- Every wiki article ends with a `## Key Takeaways` section.
- Filenames: `lowercase-with-hyphens.md`
- Preserve my voice when cleaning up dictated input.

## On query

Read `_master-index.md` → topic `_index.md` → relevant articles, in that order. Synthesize from there.

## On audit

Walk the wiki. Flag inconsistencies, broken links, gaps, and any topics referenced but missing their own article. Don't edit — just report.

## Maintenance schedule

Three recurring jobs keep the vault healthy without manual effort.

### Daily — ingest (morning)

- Sweep `raw/` into the wiki
- New clips, notes, voice memos get turned into wiki pages
- Update topic indexes and `_master-index.md`
- Goal: keep the inbox from metastasizing

### Nightly — review

- Refresh indexes
- Log gaps and broken links
- Tighten dashboards
- Update agent memory
- Catch anything that didn't get cross-linked
- Goal: tomorrow's queries start clean

### Weekly — audit (Sunday)

- Full lint of the wiki
- Flag conflicting claims, dead links, missing articles
- Identify topics worth opening up
- Output a focus list for next week
- Goal: set direction, trim noise, keep what compounds
