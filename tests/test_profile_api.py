"""Phase 8 tests: profile engine, reminders, review queue, audit, export, seeds.

Covers the feature extensions in 06-additional-features.md as implemented on
the existing graph/SQLite stack (bi-temporal profile fields, relationship
graph, goal check-ins, unified reminders, contradiction review queue with
explicit accept/reject, append-only audit log, zipped data export, and the
09/10 canonical-profile seed).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.api.routes_documents as documents_routes
import backend.api.routes_profile as profile_routes
import backend.api.routes_query as query_routes
from backend.config import settings
from backend.main import app
from backend.memory.community import CommunityStore
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.memory.profile import USER_ID, ProfileStore
from backend.memory.profile_seeds import PROFILE_FIELDS, QUEUE_ROWS, load_seeds
from backend.memory.review_queue import ReviewQueue
from backend.pipeline import Pipeline
from backend.retrieval.bm25 import BM25Index


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh pipeline + profile/audit/queue paths inside tmp."""
    for attr, value in {
        "audit_log_path": tmp_path / "audit.log.jsonl",
        "review_queue_path": tmp_path / "contradictions.json",
        "blob_dir": tmp_path / "documents",
        "blob_key": "test-passphrase",
        "auth_enabled": True,
        "auth_password_hash": "sha256:not-the-default",
        "whatsapp_access_token": "",
        "allow_insecure": False,
    }.items():
        monkeypatch.setattr(settings, attr, value, raising=False)

    pipeline = Pipeline(
        episodic_store=EpisodicStore(persist_dir=str(tmp_path / "chroma")),
        bm25_index=BM25Index(),
        graph=TemporalGraph(),
        community=CommunityStore(),
    )
    monkeypatch.setattr(profile_routes, "get_pipeline", lambda: pipeline)
    monkeypatch.setattr(documents_routes, "get_pipeline", lambda: pipeline)
    monkeypatch.setattr(query_routes, "get_pipeline", lambda: pipeline)

    return SimpleNamespace(pipeline=pipeline, tmp=tmp_path)


# ── Profile fields (bi-temporal) ─────────────────────────────────────


class TestProfileFields:
    def test_set_and_get_field(self, env):
        with TestClient(app) as client:
            resp = client.post("/profile", json={"field": "full_name", "value": "Ayush Kumar"})
            assert resp.status_code == 200
            got = client.get("/profile").json()
        assert got["fields"]["full_name"] == "Ayush Kumar"
        assert got["user_id"] == USER_ID

    def test_history_supersedes_not_overwrites(self, env):
        with TestClient(app) as client:
            client.post("/profile", json={"field": "current_address", "value": "Patna, Bihar"})
            client.post("/profile", json={"field": "current_address", "value": "Pune, Maharashtra"})
            history = client.get("/profile/history", params={"field": "current_address"}).json()
            current = client.get("/profile").json()["fields"]

        assert current["current_address"] == "Pune, Maharashtra"
        assert history["total"] == 2
        values = [h["value"] for h in history["history"]]
        assert "Pune, Maharashtra" in values and "Patna, Bihar" in values
        closed = next(h for h in history["history"] if h["value"] == "Patna, Bihar")
        assert closed["superseded_by"]  # old row kept, window closed
        assert closed["valid_to"]

    def test_identical_value_is_idempotent(self, env):
        with TestClient(app) as client:
            client.post("/profile", json={"field": "full_name", "value": "Ayush Kumar"})
            again = client.post("/profile", json={"field": "full_name", "value": "Ayush Kumar"})
            history = client.get("/profile/history", params={"field": "full_name"}).json()
        assert again.json().get("unchanged") is True
        assert history["total"] == 1

    def test_invalid_field_rejected(self, env):
        with TestClient(app) as client:
            resp = client.post("/profile", json={"field": "Bad Field!", "value": "x"})
        assert resp.status_code == 422

    def test_sensitive_field_encrypted_at_rest(self, env):
        with TestClient(app) as client:
            client.post("/profile", json={"field": "education_loan_amount", "value": "7.5 lakh"})
            shown = client.get("/profile").json()["fields"]["education_loan_amount"]

        raw_literals = [
            d.get("object_literal")
            for _, _, d in env.pipeline.graph._graph.edges(data=True)
            if d.get("predicate") == "education_loan_amount"
        ]
        assert shown == "7.5 lakh"
        assert raw_literals and raw_literals[0].startswith("enc:v1:")
        assert "7.5 lakh" not in raw_literals[0]


# ── Relationships / goals / timeline (extensions §1) ─────────────────


class TestPersonalMemoryExtras:
    def test_relationships(self, env):
        with TestClient(app) as client:
            client.post("/profile/people", json={"name": "Suman Kumar Singh", "relation": "father"})
            rels = client.get("/profile/relationships").json()
        assert rels["total"] == 1
        assert rels["relationships"][0]["relation"] == "father"
        assert rels["relationships"][0]["name"] == "Suman Kumar Singh"

    def test_goals_with_checkins(self, env):
        with TestClient(app) as client:
            gid = client.post(
                "/profile/goals",
                json={"title": "Become a software engineer", "category": "Career"},
            ).json()["goal_id"]
            client.post(f"/profile/goals/{gid}/checkins", json={"percent": 40, "note": "first third"})
            goals = client.get("/profile/goals").json()["goals"]

        goal = next(g for g in goals if g["goal_id"] == gid)
        assert goal["progress"] == 40
        assert goal["check_ins"][-1]["note"] == "first third"
        assert goal["status"] == "in_progress"

    def test_checkin_validation(self, env):
        with TestClient(app) as client:
            gid = client.post("/profile/goals", json={"title": "G"}).json()["goal_id"]
            bad = client.post(f"/profile/goals/{gid}/checkins", json={"percent": 120})
            missing = client.post("/profile/goals/nope/checkins", json={"percent": 10})
        assert bad.status_code == 422
        assert missing.status_code == 404

    def test_timeline_sorted(self, env):
        with TestClient(app) as client:
            client.post("/profile/timeline", json={"title": "Later", "event_date": "2027-01-01"})
            client.post("/profile/timeline", json={"title": "Earlier", "event_date": "2025-05-05"})
            events = client.get("/profile/timeline").json()["events"]
        assert [e["title"] for e in events] == ["Earlier", "Later"]


# ── Unified reminder feed (PRD G4) ───────────────────────────────────


class TestReminders:
    def test_reminders_merge_documents_and_goals(self, env):
        soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()
        env.pipeline.graph.add_document(
            title="rental agreement",
            usage_context="For tax filing",
            purpose_tags=["tax"],
            valid_until=soon,
        )
        with TestClient(app) as client:
            client.post(
                "/profile/goals",
                json={"title": "Apply for visa", "target_date": (datetime.now(UTC) + timedelta(days=10)).date().isoformat()},
            )
            data = client.get("/reminders", params={"window_days": 30}).json()

        kinds = {r["kind"] for r in data["reminders"]}
        assert data["window_days"] == 30
        assert "document" in kinds and "goal" in kinds
        doc_row = next(r for r in data["reminders"] if r["kind"] == "document")
        assert doc_row["urgency"] in ("red", "amber")
        assert doc_row["days_left"] <= 5

    def test_far_future_goal_excluded(self, env):
        with TestClient(app) as client:
            client.post(
                "/profile/goals",
                json={"title": "Someday", "target_date": (datetime.now(UTC) + timedelta(days=400)).date().isoformat()},
            )
            data = client.get("/reminders", params={"window_days": 30}).json()
        assert all(r["kind"] != "goal" for r in data["reminders"])


# ── Contradiction review queue (PRD G3 / §10) ────────────────────────


class TestReviewQueue:
    @pytest.fixture
    def queued(self, env):
        """Profile holds 'Ayush Kumar'; a PENDING flag proposes 'Ayush Singh'."""
        store = ProfileStore(env.pipeline.graph)
        store.set_field("full_name", "Ayush Kumar")
        row = ReviewQueue().add(
            subject=USER_ID,
            predicate="full_name",
            existing_value="Ayush Kumar",
            proposed_value="Ayush Singh",
        )
        return SimpleNamespace(**vars(env), row_id=row["id"])

    def test_list_pending(self, queued):
        with TestClient(app) as client:
            data = client.get("/contradictions").json()
        assert data["total"] == 1
        assert data["contradictions"][0]["status"] == "PENDING"
        assert data["contradictions"][0]["proposed_value"] == "Ayush Singh"
        assert data["stats"]["pending"] == 1

    def test_accept_applies_value_and_closes_old(self, queued):
        with TestClient(app) as client:
            resp = client.post(
                f"/contradictions/{queued.row_id}/resolve", json={"accept": True}
            )
            assert resp.status_code == 200
            profile = client.get("/profile").json()["fields"]
            history = client.get("/profile/history", params={"field": "full_name"}).json()

        assert profile["full_name"] == "Ayush Singh"
        old = next(h for h in history["history"] if h["value"] == "Ayush Kumar")
        assert old["superseded_by"]  # close-old, insert-new — never overwritten

    def test_reject_leaves_profile_alone(self, queued):
        with TestClient(app) as client:
            client.post(f"/contradictions/{queued.row_id}/resolve", json={"accept": False})
            profile = client.get("/profile").json()["fields"]
            stats = client.get("/contradictions", params={"status": "ALL"}).json()["stats"]

        assert profile["full_name"] == "Ayush Kumar"
        assert stats["rejected"] == 1 and stats["pending"] == 0

    def test_resolve_unknown_404_and_double_resolve_409(self, queued):
        with TestClient(app) as client:
            missing = client.post("/contradictions/cf_nope/resolve", json={"accept": True})
            client.post(f"/contradictions/{queued.row_id}/resolve", json={"accept": True})
            twice = client.post(f"/contradictions/{queued.row_id}/resolve", json={"accept": True})
        assert missing.status_code == 404
        assert twice.status_code == 409

    def test_sync_detects_graph_conflict(self, env):
        # Two active facts, same subject+predicate, different values.
        g = env.pipeline.graph
        g.add_entity(USER_ID, "User", "person")
        now = datetime.now(UTC).isoformat()
        g.add_fact(USER_ID, "jee_crl", object_literal="581383", valid_from=now)
        g.add_fact(USER_ID, "jee_crl", object_literal="581373", valid_from=now)

        with TestClient(app) as client:
            data = client.get("/contradictions").json()

        assert data["total"] >= 1
        row = data["contradictions"][0]
        assert row["predicate"] == "jee_crl"
        assert {row["existing_value"], row["proposed_value"]} == {"581383", "581373"}


# ── Audit log (extensions §4) ────────────────────────────────────────


class TestAuditLog:
    def test_query_and_profile_edit_logged(self, env):
        with TestClient(app) as client:
            client.post("/profile", json={"field": "full_name", "value": "Ayush Kumar"})
            client.post("/query", json={"query": "what is my college"})
            entries = client.get("/audit-log").json()["entries"]

        actions = [e["action"] for e in entries]
        assert "edit_profile" in actions and "query" in actions
        query_row = next(e for e in entries if e["action"] == "query")
        assert query_row["query_text"] == "what is my college"
        # newest first
        assert entries == sorted(entries, key=lambda e: e["at"], reverse=True)

    def test_document_view_logged(self, env):
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "VISA APPROVAL")
        blob = doc.tobytes()
        doc.close()

        from backend.ingestion.base import Capture

        result = env.pipeline.ingest_document(
            Capture(content="VISA APPROVAL", source_path="whatsapp/wamid.a",
                    source_type="whatsapp", caption="visa document"),
            filename="visa.pdf", mime_type="application/pdf",
            blob_bytes=blob, source_channel="whatsapp", use_llm=False,
        )
        with TestClient(app) as client:
            resp = client.get(f"/documents/{result['doc_id']}/file")
            entries = client.get("/audit-log").json()["entries"]

        assert resp.status_code == 200
        views = [e for e in entries if e["action"] == "view_document"]
        assert views and views[0]["target_id"] == result["doc_id"]

    def test_audit_is_append_only(self, env):
        with TestClient(app) as client:
            client.post("/profile", json={"field": "full_name", "value": "A"})
            client.post("/profile", json={"field": "full_name", "value": "B"})
            first = client.get("/audit-log").json()["logged"]
            second = client.get("/audit-log").json()["logged"]
        assert second >= first >= 2


# ── Data export (extensions §4 / TRD §7) ─────────────────────────────


class TestExport:
    def test_export_zip_contents(self, env):
        with TestClient(app) as client:
            client.post("/profile", json={"field": "full_name", "value": "Ayush Kumar"})
            resp = client.get("/export")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(zf.namelist())
        assert {"graph.json", "profile.json", "manifest.json", "contradictions.json",
                "audit.log.jsonl", "timeline.json", "goals.json",
                "relationships.json"} <= names

        profile = json.loads(zf.read("profile.json"))
        assert profile["full_name"] == "Ayush Kumar"
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["profile_fields"] == 1

        # The graph itself round-trips
        graph = json.loads(zf.read("graph.json"))
        assert any(n.get("id") == USER_ID for n in graph["nodes"])


# ── Canonical profile seed (09 / 10) ─────────────────────────────────


class TestCanonicalSeed:
    def test_seed_loads_and_is_idempotent(self, env):
        store = ProfileStore(env.pipeline.graph)
        queue = ReviewQueue()

        first = load_seeds(store, queue, graph=env.pipeline.graph)
        second = load_seeds(store, queue, graph=env.pipeline.graph)

        assert first == {
            "fields": len(PROFILE_FIELDS), "people": 2, "goals": 4,
            "events": 4, "documents": 2, "queue_rows": len(QUEUE_ROWS),
        }
        assert second["fields"] == 0
        assert second["documents"] == 0
        assert second["queue_rows"] == 0

        with TestClient(app) as client:
            profile = client.get("/profile").json()["fields"]
            goals = client.get("/profile/goals").json()["total"]
            timeline = client.get("/profile/timeline").json()["total"]
            docs = client.get("/documents").json()["total"]
            pending = client.get("/contradictions").json()["total"]

        assert profile["current_college"].startswith("Newton School of Technology")
        assert profile["expected_graduation_year"] == "2029"
        assert goals == 4
        assert timeline == 4
        assert docs == 2
        assert pending == len(QUEUE_ROWS)  # every conflict left for the user

    def test_seeded_contradiction_resolve_roundtrip(self, env):
        store = ProfileStore(env.pipeline.graph)
        queue = ReviewQueue()
        load_seeds(store, queue, graph=env.pipeline.graph)

        row = next(
            r for r in queue.list()
            if r["profile_field"] == "education_loan_amount"
        )
        resolved = queue.resolve(row["id"], accept=True, graph=env.pipeline.graph)

        assert resolved["status"] == "ACCEPTED"
        assert store.get_field("education_loan_amount") == "20 lakh+ (Doc B)"
        # still encrypted at rest
        raw = store.history("education_loan_amount")
        assert len(raw) == 1  # old "7.5 lakh" was never a seeded active fact

    def test_seed_dry_run_flag(self):
        import sys

        from backend.memory.profile_seeds import main as seed_main

        argv = sys.argv
        sys.argv = ["profile_seeds", "--dry-run"]
        try:
            seed_main()  # must not touch the pipeline
        finally:
            sys.argv = argv
