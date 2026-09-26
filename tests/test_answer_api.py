"""Tests for answer generation: routing, sessions, and POST /query/answer."""

from fastapi.testclient import TestClient

import pytest

from backend.answer.generation import build_context, build_messages
from backend.answer.routing import LLMUnavailableError, RouteDecision, route_llm
from backend.answer.sessions import SessionStore
from backend.config import settings
from backend.retrieval.hybrid import SearchResult

# ── Pipeline fixture (same pattern as test_api.py) ──────────────────

from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.memory.community import CommunityStore
from backend.retrieval.bm25 import BM25Index
from backend.pipeline import Pipeline

_store = EpisodicStore(persist_dir="/tmp/test_answer_episodic")
_store.reset()
_test_pipeline = Pipeline(
    episodic_store=_store,
    bm25_index=BM25Index(),
    graph=TemporalGraph(),
    community=CommunityStore(),
)

import backend.api.routes_ingest
import backend.api.routes_query

backend.api.routes_ingest.get_pipeline = lambda: _test_pipeline
backend.api.routes_query.get_pipeline = lambda: _test_pipeline

from backend.main import app  # noqa: E402  (after pipeline patching)


def _result(i: int, text: str, metadata: dict | None = None) -> SearchResult:
    return SearchResult(
        id=f"chunk_{i}",
        text=text,
        score=0.9 - i * 0.1,
        source="dense",
        metadata=metadata or {},
    )


# ── Privacy-tiered routing (06 §3) ──────────────────────────────────


class TestRouteLLM:
    def test_non_sensitive_routes_cloud(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(settings, "local_llm_base_url", "http://localhost:11434/v1")
        decision = route_llm("what did I write about transformers", [_result(0, "chunk")])
        assert decision.provider == "cloud"
        assert decision.sensitive is False
        assert decision.fallback_from is None

    def test_sensitive_purpose_tag_routes_local(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(settings, "local_llm_base_url", "http://localhost:11434/v1")
        results = [_result(0, "aadhaar", {"purpose_tags": ["identity"]})]
        decision = route_llm("when does this expire", results)
        assert decision.provider == "local"
        assert decision.sensitive is True

    def test_sensitive_question_routes_local(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(settings, "local_llm_base_url", "http://localhost:11434/v1")
        decision = route_llm("what is my passport number?", [_result(0, "x")])
        assert decision.provider == "local"
        assert decision.sensitive is True

    def test_fallback_when_preferred_tier_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(settings, "local_llm_base_url", "")  # no local tier
        results = [_result(0, "x", {"purpose_tags": ["medical"]})]
        decision = route_llm("how much was the bill", results)
        assert decision.provider == "cloud"
        assert decision.fallback_from == "local"
        assert "fell back" in decision.reason

    def test_no_provider_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "local_llm_base_url", "")
        with pytest.raises(LLMUnavailableError):
            route_llm("anything", [_result(0, "x")])

    def test_decision_serializes_for_api(self):
        d = RouteDecision(provider="cloud", model="m", reason="r", sensitive=False)
        assert d.as_dict()["provider"] == "cloud"


# ── Conversation memory (06 §3) ─────────────────────────────────────


class TestSessionStore:
    def test_creates_session_and_replays_history(self):
        store = SessionStore(ttl_seconds=3600, max_turns=8)
        sid, history = store.get_or_create(None)
        assert sid and history == []
        store.append(sid, "what's my rent?", "12000")
        sid2, history = store.get_or_create(sid)
        assert sid2 == sid
        assert [(t.role, t.content) for t in history] == [
            ("user", "what's my rent?"),
            ("assistant", "12000"),
        ]

    def test_unknown_session_id_gets_new_session(self):
        store = SessionStore()
        sid, history = store.get_or_create("does-not-exist")
        assert sid != "does-not-exist"
        assert history == []

    def test_history_capped_at_max_turns(self):
        store = SessionStore(ttl_seconds=3600, max_turns=2)
        sid, _ = store.get_or_create(None)
        for i in range(5):
            store.append(sid, f"q{i}", f"a{i}")
        _, history = store.get_or_create(sid)
        assert len(history) == 4  # 2 turns × 2 messages
        assert history[0].content == "q3"

    def test_idle_session_expires(self):
        # Negative TTL ⇒ cutoff is in the future ⇒ any session is stale,
        # deterministically (ttl=0 can race same-microsecond timestamps).
        store = SessionStore(ttl_seconds=-1, max_turns=8)
        sid, _ = store.get_or_create(None)
        store.append(sid, "q", "a")
        _, history = store.get_or_create(sid)
        assert history == []  # expired → fresh session


# ── Context / prompt building ───────────────────────────────────────


class TestPromptBuilding:
    def test_context_numbers_results(self):
        ctx = build_context([_result(0, "alpha"), _result(1, "beta")])
        assert "[1] (dense" in ctx and "[2] (dense" in ctx
        assert "alpha" in ctx and "beta" in ctx

    def test_messages_include_history_and_evidence(self):
        from backend.answer.sessions import Turn

        history = [Turn(role="user", content="prev q"), Turn(role="assistant", content="prev a")]
        messages = build_messages("follow-up", [_result(0, "fact")], history)
        assert messages[0]["role"] == "user"
        assert messages[-1]["role"] == "user"
        assert "[1]" in messages[-1]["content"]
        assert "follow-up" in messages[-1]["content"]

    def test_empty_results_note_no_evidence(self):
        messages = build_messages("q", [], [])
        assert "no relevant evidence" in messages[-1]["content"]


# ── POST /query/answer ──────────────────────────────────────────────


class TestAnswerEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_answer_with_citations_and_route(self, monkeypatch):
        canned = [_result(0, "Rent is 12000 per month"), _result(1, "Lease ends 2027-03")]
        monkeypatch.setattr(backend.api.routes_query, "_run_search", lambda *a, **k: canned)
        monkeypatch.setattr(
            backend.api.routes_query,
            "route_llm",
            lambda q, r: RouteDecision(provider="cloud", model="m", reason="r", sensitive=False),
        )
        monkeypatch.setattr(
            backend.api.routes_query,
            "generate_answer",
            lambda q, r, h, d: type("A", (), {"answer": "Rent is 12000 [1]", "context_used": 2})(),
        )
        resp = self.client.post(
            "/query/answer", json={"question": "what is my rent?"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Rent is 12000 [1]"
        assert len(data["citations"]) == 2
        assert data["citations"][0]["index"] == 1
        assert data["route"]["provider"] == "cloud"
        assert data["session_id"]
        assert data["results_total"] == 2

    def test_follow_up_reuses_session_history(self, monkeypatch):
        canned = [_result(0, "fact")]
        monkeypatch.setattr(backend.api.routes_query, "_run_search", lambda *a, **k: canned)
        monkeypatch.setattr(
            backend.api.routes_query,
            "route_llm",
            lambda q, r: RouteDecision(provider="cloud", model="m", reason="r", sensitive=False),
        )
        captured: list[list] = []

        def fake_generate(q, r, history, d):
            captured.append(list(history))
            return type("A", (), {"answer": f"answer-{len(captured)}", "context_used": 1})()

        monkeypatch.setattr(backend.api.routes_query, "generate_answer", fake_generate)

        first = self.client.post("/query/answer", json={"question": "what's my rent?"}).json()
        second = self.client.post(
            "/query/answer",
            json={"question": "and the deposit?", "session_id": first["session_id"]},
        ).json()

        assert second["session_id"] == first["session_id"]
        # Second call saw the first exchange as conversation memory
        roles = [(t.role, t.content) for t in captured[1]]
        assert ("user", "what's my rent?") in roles
        assert ("assistant", "answer-1") in roles

    def test_no_results_skips_model(self, monkeypatch):
        monkeypatch.setattr(backend.api.routes_query, "_run_search", lambda *a, **k: [])

        def must_not_call(*a, **k):
            raise AssertionError("route_llm should not be called without results")

        monkeypatch.setattr(backend.api.routes_query, "route_llm", must_not_call)
        monkeypatch.setattr(backend.api.routes_query, "generate_answer", must_not_call)
        resp = self.client.post("/query/answer", json={"question": "unfindable"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["route"]["provider"] == "none"
        assert data["citations"] == []
        assert "couldn't find" in data["answer"]

    def test_returns_503_when_no_llm_configured(self, monkeypatch):
        canned = [_result(0, "fact")]
        monkeypatch.setattr(backend.api.routes_query, "_run_search", lambda *a, **k: canned)
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "local_llm_base_url", "")
        resp = self.client.post("/query/answer", json={"question": "anything"})
        assert resp.status_code == 503

    def test_returns_502_when_model_call_fails(self, monkeypatch):
        from backend.answer import LLMCallError

        canned = [_result(0, "fact")]
        monkeypatch.setattr(backend.api.routes_query, "_run_search", lambda *a, **k: canned)
        monkeypatch.setattr(
            backend.api.routes_query,
            "route_llm",
            lambda q, r: RouteDecision(provider="cloud", model="m", reason="r", sensitive=False),
        )

        def boom(q, r, h, d):
            raise LLMCallError("cloud model call failed: timeout")

        monkeypatch.setattr(backend.api.routes_query, "generate_answer", boom)
        resp = self.client.post("/query/answer", json={"question": "anything"})
        assert resp.status_code == 502

    def test_answer_is_audited(self, monkeypatch):
        monkeypatch.setattr(
            backend.api.routes_query, "_run_search", lambda *a, **k: [_result(0, "fact")]
        )
        monkeypatch.setattr(
            backend.api.routes_query,
            "route_llm",
            lambda q, r: RouteDecision(provider="cloud", model="m", reason="r", sensitive=False),
        )
        monkeypatch.setattr(
            backend.api.routes_query,
            "generate_answer",
            lambda q, r, h, d: type("A", (), {"answer": "a", "context_used": 1})(),
        )
        calls: list[dict] = []
        monkeypatch.setattr(
            backend.api.routes_query.audit, "record", lambda action, **kw: calls.append((action, kw))
        )
        self.client.post("/query/answer", json={"question": "q"})
        assert calls and calls[0][0] == "query_answer"

    def test_plain_query_route_still_works(self, monkeypatch):
        monkeypatch.setattr(backend.api.routes_query, "_run_search", lambda *a, **k: [])
        resp = self.client.post("/query", json={"query": "anything"})
        assert resp.status_code == 200
        assert resp.json()["results"] == []
