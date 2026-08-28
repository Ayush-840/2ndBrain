"""Integration tests for API endpoints.

Tests the API routes that the NiceGUI frontend calls, using FastAPI's
TestClient.
"""

from fastapi.testclient import TestClient

from backend.main import app
from backend.api.routes_ingest import get_pipeline
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.memory.community import CommunityStore
from backend.retrieval.bm25 import BM25Index

# Override pipeline with fresh instances for testing
_test_store = EpisodicStore(persist_dir="/tmp/test_api_episodic")
_test_store.reset()
_test_bm25 = BM25Index()
_test_graph = TemporalGraph()
_test_community = CommunityStore()

from backend.pipeline import Pipeline
_test_pipeline = Pipeline(
    episodic_store=_test_store,
    bm25_index=_test_bm25,
    graph=_test_graph,
    community=_test_community,
)

# Monkey-patch get_pipeline since routes call it directly (not as DI)
import backend.api.routes_ingest
import backend.api.routes_graph
import backend.api.routes_community
import backend.api.routes_surfacing
import backend.api.routes_query
backend.api.routes_ingest.get_pipeline = lambda: _test_pipeline
backend.api.routes_graph.get_pipeline = lambda: _test_pipeline
backend.api.routes_community.get_pipeline = lambda: _test_pipeline
backend.api.routes_surfacing.get_pipeline = lambda: _test_pipeline
backend.api.routes_query.get_pipeline = lambda: _test_pipeline


class TestRootEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_root(self):
        resp = self.client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "2ndBrain"
        assert "frontend" in data

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestIngestStats:
    def setup_method(self):
        self.client = TestClient(app)

    def test_stats(self):
        resp = self.client.get("/ingest/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "episodic_count" in data
        assert "bm25_count" in data

    def test_reset(self):
        resp = self.client.delete("/ingest/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"


class TestGraphEndpoints:
    def setup_method(self):
        self.client = TestClient(app)
        # Seed graph for testing
        _test_graph.add_entity("user", "Ayush", "person")
        _test_graph.add_entity("rag", "RAG", "concept")
        _test_graph.add_fact("user", "works_on", object_id="rag")

    def test_stats(self):
        resp = self.client.get("/graph/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entities"] >= 2
        assert data["facts"] >= 1

    def test_entities(self):
        resp = self.client.get("/graph/entities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_export(self):
        resp = self.client.get("/graph/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["elements"]) > 0
        nodes = [e for e in data["elements"] if e["group"] == "nodes"]
        edges = [e for e in data["elements"] if e["group"] == "edges"]
        assert len(nodes) >= 2
        assert len(edges) >= 1

    def test_query_as_of(self):
        resp = self.client.post(
            "/graph/query-as-of",
            json={"date": "2026-08-28"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1


class TestCommunityEndpoints:
    def setup_method(self):
        self.client = TestClient(app)

    def test_stats(self):
        resp = self.client.get("/community/stats")
        assert resp.status_code == 200

    def test_clusters_empty(self):
        resp = self.client.get("/community/clusters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestSurfacingEndpoints:
    def setup_method(self):
        self.client = TestClient(app)

    def test_contradictions(self):
        resp = self.client.post("/surfing/contradictions", json={})
        assert resp.status_code == 200

    def test_digest(self):
        resp = self.client.post(
            "/surfing/digest",
            json={"digest_type": "daily"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["digest_type"] == "daily"
        assert len(data["entries"]) > 0

    def test_resurface(self):
        resp = self.client.post(
            "/surfing/resurface",
            json={"context": "graph databases", "top_k": 5},
        )
        assert resp.status_code == 200
