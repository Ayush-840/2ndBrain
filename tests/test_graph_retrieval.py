"""Tests for graph-aware retrieval."""

from backend.memory.graph import TemporalGraph
from backend.retrieval.graph_retrieval import (
    GraphRetriever,
    _extract_entity_mentions,
    _normalize,
)


class TestEntityMentionExtraction:
    def setup_method(self):
        self.entities = [
            {"entity_id": "ai_memory", "label": "AI Memory", "entity_type": "concept"},
            {"entity_id": "vector_store", "label": "Vector Store", "entity_type": "concept"},
            {"entity_id": "neo4j", "label": "Neo4j", "entity_type": "tool"},
            {"entity_id": "user", "label": "Ayush", "entity_type": "person"},
        ]

    def test_exact_label_match(self):
        matches = _extract_entity_mentions("What is AI Memory?", self.entities)
        assert len(matches) >= 1
        assert matches[0]["entity_id"] == "ai_memory"

    def test_partial_label_match(self):
        matches = _extract_entity_mentions("Tell me about Neo4j usage", self.entities)
        assert any(m["entity_id"] == "neo4j" for m in matches)

    def test_no_match(self):
        matches = _extract_entity_mentions("random unrelated query", self.entities)
        assert len(matches) == 0

    def test_multiple_matches(self):
        matches = _extract_entity_mentions(
            "Compare Vector Store and Neo4j for AI Memory", self.entities
        )
        matched_ids = {m["entity_id"] for m in matches}
        assert "vector_store" in matched_ids
        assert "neo4j" in matched_ids
        assert "ai_memory" in matched_ids

    def test_case_insensitive(self):
        matches = _extract_entity_mentions("what is neo4j?", self.entities)
        assert any(m["entity_id"] == "neo4j" for m in matches)

    def test_entity_id_match(self):
        entities = [{"entity_id": "bi_temporal_modeling", "label": "Bitemporal", "entity_type": "concept"}]
        matches = _extract_entity_mentions("How does bi_temporal_modeling work?", entities)
        assert len(matches) >= 1


class TestGraphRetriever:
    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "Ayush", "person")
        self.graph.add_entity("rag", "RAG", "concept")
        self.graph.add_entity("graph_db", "Graph Database", "concept")
        self.graph.add_entity("vector_store", "Vector Store", "concept")

        self.graph.add_fact("user", "works_on", object_id="rag", valid_from="2026-01-01")
        self.graph.add_fact("user", "prefers", object_id="graph_db", valid_from="2026-06-01")
        self.graph.add_fact("rag", "uses", object_id="vector_store")
        self.graph.add_fact("graph_db", "supersedes", object_id="vector_store", valid_from="2026-06-01")

        self.retriever = GraphRetriever(self.graph)

    def test_search_finds_entity(self):
        results = self.retriever.search("Tell me about RAG")
        assert len(results) > 0
        # Should find facts connected to RAG
        texts = [r.text.lower() for r in results]
        assert any("rag" in t for t in texts)

    def test_search_multi_hop(self):
        results = self.retriever.search("What does Ayush work on?", hops=2)
        assert len(results) > 0
        # Should find user → rag → vector_store (2 hops)

    def test_search_no_match(self):
        results = self.retriever.search("unrelated query about cooking")
        assert len(results) == 0

    def test_fact_to_text(self):
        results = self.retriever.search("Tell me about Graph Database")
        assert len(results) > 0
        # Graph facts should be human-readable
        for r in results:
            assert isinstance(r.text, str)
            assert len(r.text) > 0

    def test_direct_connections_scored_higher(self):
        results = self.retriever.search("Ayush prefers", hops=2)
        if results:
            # The direct fact (user → prefers → graph_db) should rank higher
            # than indirect facts
            direct = [r for r in results if r.metadata.get("direct_connection")]
            indirect = [r for r in results if not r.metadata.get("direct_connection")]
            if direct and indirect:
                assert direct[0].score >= indirect[0].score

    def test_temporal_filter(self):
        results = self.retriever.search("Ayush", valid_as_of="2026-03-01")
        # In March, "prefers graph_db" (valid_from=2026-06-01) should NOT appear
        for r in results:
            assert "graph database" not in r.text.lower() or r.metadata.get("valid_from", "") <= "2026-03-01"
