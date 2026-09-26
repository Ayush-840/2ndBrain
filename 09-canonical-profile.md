# Canonical Profile — Reconciled from Both Uploaded Documents

**Sources:** `Ayush_Kumar_Personal_Second_Brain_Profile.pdf` (Doc A) and `Ayush_Second_Brain_Profile.pdf` (Doc B), both dated 26 Sept 2026.
**Method:** merged using the `category / fact / status / date / source / confidence / supersedes` schema Doc B itself proposes in its §16 — this is that schema applied to your own data, not a new format invented on top of it.
**Handling note:** both source PDFs say this contains personal, academic, and administrative details and should stay private/access-controlled — treated that way here; nothing sensitive is repeated outside this working file.

---

## 1. Identity

| Fact | Status | Confidence | Note |
|---|---|---|---|
| Name: **Ayush Kumar** | uncertain | medium | Doc A: "account profile also displays Ayush Singh." **Unresolved — needs your confirmation before use on any public/official document.** |
| Home/origin: Bihar | current | high | Doc A says Patna; Doc B references Chapra. Region (Bihar) is high-confidence; the specific town is **conflicting, low confidence.** |
| Current location: Pune, Maharashtra | uncertain | low | Doc A explicitly flags this as estimated from usage metadata, not a verified address. |
| College: Newton School of Technology (NST), ADYPU Pune | current | high | Confirmed consistently in both docs — the most stable fact in either file. |
| Program: B.Tech, CSE with AI/ML focus, 2nd year (as of Sep 2026) | current | high | Consistent across both. |
| Expected study period: 2025–2029 | current | medium | Only in Doc A. |
| GitHub: Ayush-840 | current | high | Consistent. |

## 2. Education Timeline (Historical / Admissions — treat as history, not current status)

| Fact | Status | Confidence | Source |
|---|---|---|---|
| Class 12: BSEB Science, 82% (410 marks) | current | high | Both docs agree — one of the few clean numeric matches. |
| JEE Main CRL ~581,373–581,383, GEN-EWS rank 76,036 | historical | medium | Both docs, minor digit variance between them. |
| Later AKTU-related CRL ~342,932, interest in ECE at GL Bajaj | historical | low | Doc B only — unclear if this supersedes or is a separate application track. |
| BITSAT: 245 (one message) vs. 56 (later message) | historical | **low — direct contradiction** | Doc B flags this itself as conflicting. Needs you to confirm which, if either, is correct. |
| NST NSAT: 7.16/10, shortlisted | historical | medium | Doc B only. |
| Scaler NSET 2025: self-reported ~20–21 correct (~60%) vs. portal showing 11 | historical | **low — direct contradiction** | Doc B; user reportedly wanted to draft a complaint email about this discrepancy. |
| Other institutions considered: SRM KTR, CU, Plaksha, SNU, PW IOI, Polaris, Vedam, GL Bajaj, Symbiosis, KIIT, Manipal-related, MIT-WPU/PVG | historical | medium | Doc B only. |

**Resolution used going forward:** NST Pune is the current, stable academic fact. Everything else in this section is retained as admissions *history*, not present status — consistent with both documents' own instruction not to treat old scores as guaranteed current.

## 3. Career Direction & Personality

| Fact | Status | Confidence |
|---|---|---|
| Goal: become a successful software engineer, build practical/real-life-useful applications | current | high (both docs agree) |
| ~4–5 year career-development horizon (Doc B) | historical | medium |
| Strengths (self-described): dedicated, hardworking, action-oriented, responsible, fast learner, consistent once a goal is set | current | high |
| Growth area: overthinking before starting; focus improves once started | current | high (both docs agree independently — strong signal) |
| Preferred support style: small first steps, clear starting point, progress checkpoints, not overwhelming lists | current | high |

## 4. Learning & Teaching Preferences (high-confidence, very consistent across both docs)

- Beginner-first, step-by-step, teacher/professor-style explanations.
- Pattern-first for DSA: identify the pattern → template → practice problems.
- Simple, readable code; explicitly avoids unnecessary cleverness (e.g., avoids `collections`/`defaultdict`/`set` when not needed; no unneeded imports).
- Wants dry runs, visual representations (tree/array), worked examples, and exam-style step-by-step math solutions.
- Prefers simple English / Hinglish for casual and difficult-concept explanations; wants to improve formal English communication specifically.
- Says "next" to continue an established sequence rather than restart — **the system should track "current lesson position," not just topic completion.**
- Wants structured, genuinely useful PDFs/notes, not shallow outlines converted to PDF.

## 5. Technical Skill Snapshot (current, high confidence — consistent across both docs)

- **Languages/stacks:** Python (primary, both docs), Node.js/Express/MVC, PostgreSQL 16.15 (Homebrew, macOS).
- **DSA:** Graphs (BFS/DFS, shortest path, grid BFS, mother vertex, transitive closure, k-cores), Trees/BSTs, Backtracking (subsets, permutations, palindrome partitioning), Sorting (Quick/Merge/Heap), Heaps (min/max, top-k, merge-k, two-heap median pattern), Linked Lists, Master Theorem/recurrence analysis.
- **Math:** Linear algebra (matrices, Gaussian elimination, rank/nullity, vector spaces, LU decomposition — "column picture" specifically preferred), Discrete math (truth tables, sets, probability, distributions).
- **DB:** SELECT/WHERE/GROUP BY/HAVING/CASE/window functions, joins, subqueries, NULL/anti-join patterns.
- **Environment:** MacBook/macOS, zsh, Git/GitHub; has tried Aider (0.86.2), Qwen Code (0.24.4, hit DashScope auth errors), OpenCode (1.18.29); hit free-tier OpenRouter rate limits.
- **Competitive programming:** Interested in Algonauts (NST's CP club) — 3-phase entry (Aptitude → Training → Coding Challenge); Codeforces/LeetCode pattern practice.

## 6. Projects

| Project | Status | Detail |
|---|---|---|
| **KnowledgeRAG** (`Ayush-840/KnowledgeRAG`) | uncertain | Local RAG/VectorMind effort; a README merge conflict was in progress last mentioned. |
| **nst-code-ext** | uncertain | Express-based extension/API project: auth, admin, GitHub integration, tests; rebase conflicts discussed. |
| **code_x** (`Ayush-840/code_x`) | uncertain, likely most recently active | Full-stack "AI Lab OS" dashboard; API worker, WebSocket, Python service, Prisma, CI, Railway deploy; health check returned 200 on port 4000; as of 24 Sep 2026, `main` reported clean, tracking `origin/main`, latest commit `52abb3f`. |
| **Substation Maintenance Chatbot** | exploratory | RAG/catalog-based prototype for transformer/reactor/breaker maintenance knowledge; a known failure mode (off-topic prompts returning a transformer IR/PI template) was identified, with a plan to produce an evaluation/failure report. |
| **2ndBrain** (this project) | active | The system this whole PRD/TRD series is being built for. |
| **College project (30-mark) — undecided** | open | Candidates discussed: geolocation attendance tracking, live location tracking, railway station navigation, LAN file transfer (local discovery, resumable, integrity-checked). Wants complete docs (PRD/TRD/design.md) once chosen. |

## 7. Administrative / Financial (private — access-controlled only)

| Fact | Status | Confidence | Note |
|---|---|---|---|
| Education loan amount | historical | **low — direct contradiction** | Doc A: ₹7.5 lakh, guarantor father Suman Kumar Singh. Doc B: exploring a loan "in the ₹20 lakh+ range," Vidya Lakshmi portal, income certificate/ITR docs. **These may refer to different points in time or different loan stages — needs your confirmation, not an assumption.** |
| JEE Main CRL / EWS rank / Class 12 domicile (Bihar) | historical | medium | See §2. |

Both source documents independently flag this category as sensitive and recommend keeping it out of public-facing profiles — treated that way here.

## 8. Social / Personal Context (private)

- Relationship mentioned: a partner named Sanchita, described positively.
- Has discussed missing family after relocating for college; values messages/statuses around that transition.
- Uses Instagram; wants concise English/Hinglish captions/bios.
- Health note (Doc A only): had typhoid mid-semester, missed graded work, recovered and improved end-semester performance — offered as an interview story, not flagged as an ongoing condition.

## 9. Open Items to Confirm (merged from both documents' own "gaps" sections)

1. Preferred name for official use: **Ayush Kumar vs. Ayush Singh.**
2. Current semester/year and expected graduation date.
3. Verified current city/residence (Pune is unverified).
4. Which projects (§6) are active vs. paused vs. abandoned.
5. Current study schedule — the weekday 9:30 PM–2:30 AM plan in Doc A is explicitly marked "previously requested," not confirmed current.
6. Resolve the BITSAT (245 vs. 56) and Scaler NSET (self-reported vs. portal) discrepancies, or accept both as permanently "uncertain — historical."
7. Resolve the loan amount discrepancy (₹7.5L vs. ₹20L+), and confirm whether admin/financial details should be stored in the system at all (Doc A raises this explicitly).

---

**How this should be used going forward:** treat this file as the seed for `user_profile`/`personal_goals`/`timeline_events` (see `10-seed-data.md`), not as a finished, locked record. Every row marked "uncertain" or "historical" above should show up in the system's own `contradiction_flags` review queue, not be silently picked one way — exactly the behavior the PRD/TRD were designed around, and exactly what Doc B's own §15–16 asked for.
