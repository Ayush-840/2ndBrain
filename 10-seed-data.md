# Seed Data — Loading This Profile Into the System's Own Schema

This takes `09-canonical-profile.md` and expresses it as actual rows in the schema defined in `08-trd.md` §3. IDs below are readable placeholders (`uuid-...`) for documentation clarity — generate real UUIDs at insert time. This is meant to be the first real data the system ever holds, and it deliberately demonstrates the contradiction-detection feature working on your own real, conflicting source documents rather than a toy example.

---

## 1. `user_profile`

```sql
INSERT INTO user_profile (
    id, full_name, dob, permanent_address, current_address,
    current_college, degree_pursuing, field_of_study, expected_graduation_year,
    valid_from, valid_to
) VALUES (
    'uuid-user-1',
    'Ayush Kumar',                          -- unresolved vs "Ayush Singh" -- see contradiction_flags below
    NULL,                                   -- not present in either source document
    'Bihar, India',                         -- town-level detail conflicting (Patna vs Chapra) -- kept region-only
    'Pune, Maharashtra, India',              -- marked low-confidence/estimated, not verified
    'Newton School of Technology (NST), ADYPU Pune',
    'B.Tech, CSE (AI/ML focus)',
    'Computer Science and Engineering',
    2029,
    now(), NULL
);
```

## 2. `family_members` + `relationships`

```sql
INSERT INTO family_members (id, user_id, name, relation, contact_number, additional_notes) VALUES
    ('uuid-fam-1', 'uuid-user-1', 'Suman Kumar Singh', 'father', NULL, 'Loan guarantor (see contradiction_flags: loan amount unresolved)'),
    ('uuid-fam-2', 'uuid-user-1', 'Sanchita', 'partner', NULL, 'Described positively; personal/private category');

INSERT INTO relationships (id, person_a_id, person_b_id, relation_type, valid_from, valid_to) VALUES
    ('uuid-rel-1', 'uuid-user-1', 'uuid-fam-1', 'guarantor_of_loan', now(), NULL);
```

## 3. `personal_goals`

```sql
INSERT INTO personal_goals (id, user_id, category, title, description, target_date, status) VALUES
    ('uuid-goal-1', 'uuid-user-1', 'Career', 'Become a successful software engineer',
     'Build practical, real-world applications; make college and future company proud.', NULL, 'IN_PROGRESS'),
    ('uuid-goal-2', 'uuid-user-1', 'Academic', 'Improve semester performance',
     'Targeted a 50/50 score on a specific course/assessment after feeling grades under-represented effort.', NULL, 'IN_PROGRESS'),
    ('uuid-goal-3', 'uuid-user-1', 'Competitive Programming', 'Join Algonauts CP club',
     'NST competitive programming club: Aptitude round -> Training -> Coding Challenge.', NULL, 'IN_PROGRESS'),
    ('uuid-goal-4', 'uuid-user-1', 'Personal', 'Improve English communication',
     'Self-identified growth area; wants stronger formal English alongside preferred Hinglish explanations.', NULL, 'IN_PROGRESS');
```

## 4. `timeline_events`

```sql
INSERT INTO timeline_events (id, user_id, event_title, event_date, category, detailed_description, associated_document_id) VALUES
    ('uuid-tl-1', 'uuid-user-1', 'Completed Class 12 (BSEB Science)', NULL, 'Education', '82% / 410 marks.', NULL),
    ('uuid-tl-2', 'uuid-user-1', 'Joined Newton School of Technology, Pune', NULL, 'Education', 'Chose NST Pune campus over Bangalore option after NSAT (7.16/10) and interview.', NULL),
    ('uuid-tl-3', 'uuid-user-1', 'code_x deployment health check passed', '2026-09-24', 'Project', 'Local repo clean on main, tracking origin/main, commit 52abb3f. Deployment returned HTTP 200 on port 4000 (Railway).', NULL),
    ('uuid-tl-4', 'uuid-user-1', 'Mid-semester illness (typhoid)', NULL, 'Personal', 'Missed graded projects for about a month; resumed studying and exceeded own end-semester expectations.', NULL);
```

## 5. `documents` — the two source PDFs themselves

```sql
INSERT INTO documents (id, file_name, file_path, mime_type, category, detailed_description, tags, source_channel, confidence_score, key_dates) VALUES
    ('uuid-doc-1', 'Ayush_Kumar_Personal_Second_Brain_Profile.pdf', '/vault/profile/doc_a.pdf', 'application/pdf',
     'Identity', 'Consolidated personal/academic/admin context, prepared 26 Sep 2026 for Second Brain import.',
     ARRAY['profile','identity','education','admin'], 'upload', 0.7, NULL),
    ('uuid-doc-2', 'Ayush_Second_Brain_Profile.pdf', '/vault/profile/doc_b.pdf', 'application/pdf',
     'Identity', 'Consolidated personal/academic/learning/career context, prepared 26 Sep 2026, proposes its own memory metadata schema.',
     ARRAY['profile','identity','education','learning-preferences'], 'upload', 0.7, NULL);
```

## 6. `contradiction_flags` — populated from the real conflicts found

This is the part worth paying attention to: rather than resolving the discrepancies between your two documents silently, the system logs each one exactly the way it would for any two conflicting documents, so you confirm rather than the system guessing.

```sql
INSERT INTO contradiction_flags (id, document_id, profile_table, profile_field, existing_value, proposed_value, status) VALUES
    ('uuid-cf-1', 'uuid-doc-1', 'user_profile', 'full_name', 'Ayush Kumar', 'Ayush Singh', 'PENDING'),
    ('uuid-cf-2', 'uuid-doc-1', 'user_profile', 'permanent_address', 'Patna, Bihar', 'Chapra, Bihar (Doc B)', 'PENDING'),
    ('uuid-cf-3', 'uuid-doc-2', 'timeline_events', 'BITSAT_score', '245', '56', 'PENDING'),
    ('uuid-cf-4', 'uuid-doc-2', 'timeline_events', 'Scaler_NSET_score', '~20-21 correct (~60%)', '11 (per portal)', 'PENDING'),
    ('uuid-cf-5', 'uuid-doc-1', 'admin_financial', 'education_loan_amount', '7.5 lakh (Doc A)', '20 lakh+ (Doc B)', 'PENDING'),
    ('uuid-cf-6', 'uuid-doc-2', 'user_profile', 'jee_crl', '581383 (Doc A)', '581373 (Doc B, approx.)', 'PENDING');
```

Every row above stays `PENDING` until you resolve it via `POST /contradictions/{id}/resolve` (from the TRD's API) — exactly the same flow that would trigger for a brand-new document uploaded next month. Nothing here is auto-accepted.

## 7. What was deliberately left out of this seed

Per both source documents' own privacy instructions, the following were kept in the canonical profile as *context* but not turned into structured, queryable rows here: exact JEE percentile/rank digits beyond what's needed for historical reference, and any account/password/secret data (neither document contained any, by their own statement). The admin/financial category (§7 of the canonical profile) is seeded above only as a flagged contradiction, not as a confirmed `personal_goals` or `documents` entry — per Doc A's own suggestion, this should wait for your explicit confirmation that it belongs in the system at all.
