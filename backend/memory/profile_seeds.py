"""Canonical profile seed — ``09-canonical-profile.md`` / ``10-seed-data.md``.

Loads the first real data the system holds: identity, family, goals,
timeline, the two source documents, and the six *unresolved* conflicts
between them — deliberately left PENDING so the contradiction review
queue demonstrates itself rather than silently picking a side (PRD §10).

Run with::

    python3 -m backend.memory.profile_seeds            # seed data/graph.db
    python3 -m backend.memory.profile_seeds --dry-run  # show what would load

Uncertain facts from the canonical profile are seeded exactly as written
there — nothing in this module resolves a conflict on the user's behalf.
"""

from __future__ import annotations

import argparse

from backend.memory.profile import USER_ID, ProfileStore
from backend.memory.review_queue import ReviewQueue

# §1 user_profile — as-is from 10-seed-data.md (region-only permanent address;
# "Ayush Kumar" stays flagged against "Ayush Singh" via QUEUE_ROWS below).
PROFILE_FIELDS: dict[str, str] = {
    "full_name": "Ayush Kumar",
    "permanent_address": "Bihar, India",
    "current_address": "Pune, Maharashtra, India",
    "current_college": "Newton School of Technology (NST), ADYPU Pune",
    "degree_pursuing": "B.Tech, CSE (AI/ML focus)",
    "field_of_study": "Computer Science and Engineering",
    "expected_graduation_year": "2029",
}

# §2 family_members (+ one explicit relationship edge, §2 relationships row)
PEOPLE: list[dict] = [
    {
        "name": "Suman Kumar Singh",
        "relation": "father",
        "notes": "Loan guarantor (see contradictions: loan amount unresolved)",
        "extra_relation": "guarantor_of_loan",
    },
    {
        "name": "Sanchita",
        "relation": "partner",
        "notes": "Described positively; personal/private category",
    },
]

# §3 personal_goals
GOALS: list[dict] = [
    {
        "title": "Become a successful software engineer",
        "category": "Career",
        "description": "Build practical, real-world applications; make college and future company proud.",
    },
    {
        "title": "Improve semester performance",
        "category": "Academic",
        "description": "Targeted a 50/50 score on a specific course/assessment after feeling grades under-represented effort.",
    },
    {
        "title": "Join Algonauts CP club",
        "category": "Competitive Programming",
        "description": "NST competitive programming club: Aptitude round -> Training -> Coding Challenge.",
    },
    {
        "title": "Improve English communication",
        "category": "Personal",
        "description": "Self-identified growth area; wants stronger formal English alongside preferred Hinglish explanations.",
    },
]

# §4 timeline_events
EVENTS: list[dict] = [
    {"title": "Completed Class 12 (BSEB Science)", "category": "Education",
     "description": "82% / 410 marks."},
    {"title": "Joined Newton School of Technology, Pune", "category": "Education",
     "description": "Chose NST Pune campus over Bangalore option after NSAT (7.16/10) and interview."},
    {"title": "code_x deployment health check passed", "event_date": "2026-09-24",
     "category": "Project",
     "description": "Local repo clean on main, tracking origin/main, commit 52abb3f. Deployment returned HTTP 200 on port 4000 (Railway)."},
    {"title": "Mid-semester illness (typhoid)", "category": "Personal",
     "description": "Missed graded projects for about a month; resumed studying and exceeded own end-semester expectations."},
]

# §5 documents — metadata records for the two source PDFs themselves.
SEED_DOCUMENTS: list[dict] = [
    {
        "title": "Ayush Kumar Personal Second Brain Profile",
        "filename": "Ayush_Kumar_Personal_Second_Brain_Profile.pdf",
        "usage_context": "Profile import source A, prepared 26 Sep 2026",
        "purpose_tags": ["profile", "identity", "education", "admin"],
        "source_channel": "upload",
        "episodic_ref": "seed-doc-a",
    },
    {
        "title": "Ayush Second Brain Profile",
        "filename": "Ayush_Second_Brain_Profile.pdf",
        "usage_context": "Profile import source B, prepared 26 Sep 2026",
        "purpose_tags": ["profile", "identity", "education", "learning-preferences"],
        "source_channel": "upload",
        "episodic_ref": "seed-doc-b",
    },
]

# §6 contradiction_flags — every conflict, left PENDING for the user.
QUEUE_ROWS: list[dict] = [
    {"profile_table": "user_profile", "profile_field": "full_name",
     "existing_value": "Ayush Kumar", "proposed_value": "Ayush Singh"},
    {"profile_table": "user_profile", "profile_field": "permanent_address",
     "existing_value": "Patna, Bihar", "proposed_value": "Chapra, Bihar (Doc B)"},
    {"profile_table": "timeline_events", "profile_field": "BITSAT_score",
     "existing_value": "245", "proposed_value": "56"},
    {"profile_table": "timeline_events", "profile_field": "Scaler_NSET_score",
     "existing_value": "~20-21 correct (~60%)", "proposed_value": "11 (per portal)"},
    {"profile_table": "admin_financial", "profile_field": "education_loan_amount",
     "existing_value": "7.5 lakh (Doc A)", "proposed_value": "20 lakh+ (Doc B)"},
    {"profile_table": "user_profile", "profile_field": "jee_crl",
     "existing_value": "581383 (Doc A)", "proposed_value": "581373 (Doc B, approx.)"},
]


def load_seeds(
    profile: ProfileStore,
    queue: ReviewQueue | None = None,
    *,
    graph=None,
    documents: bool = True,
) -> dict:
    """Idempotent: re-running does not duplicate facts, rows or documents.

    Counts are *new* items (profile counts are diffed before/after), so a
    second run reports zeroes across the board.
    """
    before = profile.counts()

    for field, value in PROFILE_FIELDS.items():
        profile.set_field(field, value, source="seed")

    graph = graph or profile._graph
    for person in PEOPLE:
        pid = profile.add_person(
            person["name"], person["relation"], notes=person.get("notes", "")
        )
        if person.get("extra_relation"):
            profile._set_link(USER_ID, person["extra_relation"], pid)

    for goal in GOALS:
        profile.add_goal(
            goal["title"],
            category=goal.get("category", "General"),
            description=goal.get("description", ""),
            target_date=goal.get("target_date"),
        )

    for event in EVENTS:
        profile.add_event(
            event["title"],
            event_date=event.get("event_date"),
            category=event.get("category", "General"),
            description=event.get("description", ""),
        )

    docs_added = 0
    if documents:
        known = {
            d.get("filename")
            for d in graph.list_documents(include_superseded=True)
        }
        for spec in SEED_DOCUMENTS:
            if spec["filename"] in known:
                continue
            graph.add_document(
                title=spec["title"],
                usage_context=spec["usage_context"],
                purpose_tags=spec["purpose_tags"],
                source_channel=spec["source_channel"],
                filename=spec["filename"],
                episodic_ref=spec["episodic_ref"],
                inferred_by="seed",
            )
            known.add(spec["filename"])
            docs_added += 1

    after = profile.counts()
    summary = {key: after[key] - before[key] for key in before}
    summary["documents"] = docs_added
    summary["queue_rows"] = 0

    if queue is not None:
        existing = {
            (row.get("profile_field"), row.get("proposed_value"))
            for row in queue.list(status=None)
        }
        for row in QUEUE_ROWS:
            key = (row["profile_field"], row["proposed_value"])
            if key in existing:
                continue
            added = queue.add(
                subject=USER_ID,
                predicate=row["profile_field"],
                existing_value=row["existing_value"],
                proposed_value=row["proposed_value"],
                profile_table=row["profile_table"],
            )
            if added:
                summary["queue_rows"] += 1

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the canonical profile (09/10).")
    parser.add_argument("--dry-run", action="store_true", help="report only")
    args = parser.parse_args()

    if args.dry_run:
        print("Would seed:", len(PROFILE_FIELDS), "fields,", len(PEOPLE), "people,",
              len(GOALS), "goals,", len(EVENTS), "events,", len(SEED_DOCUMENTS),
              "documents,", len(QUEUE_ROWS), "contradiction rows")
        return

    from backend.api.routes_ingest import get_pipeline

    pipeline = get_pipeline()

    summary = load_seeds(ProfileStore(pipeline.graph), ReviewQueue(), graph=pipeline.graph)
    print("Seeded:", summary)
    print("Queue:", ReviewQueue().stats())


if __name__ == "__main__":
    main()
