"""Tests for the bi-temporal knowledge graph."""

import tempfile
from pathlib import Path

from backend.memory.graph import TemporalGraph


class TestEntityOperations:
    def setup_method(self):
        self.graph = TemporalGraph()

    def test_add_entity(self):
        eid = self.graph.add_entity("ai_memory", "AI Memory", "concept")
        assert eid == "ai_memory"
        assert self.graph.has_entity("ai_memory")

    def test_entity_slug_normalization(self):
        eid = self.graph.add_entity("Transformer Architecture", "Transformers", "technique")
        assert eid == "transformer_architecture"

    def test_get_entity(self):
        self.graph.add_entity("claude", "Claude", "tool")
        entity = self.graph.get_entity("claude")
        assert entity is not None
        assert entity["label"] == "Claude"
        assert entity["entity_type"] == "tool"

    def test_get_nonexistent_entity(self):
        assert self.graph.get_entity("nonexistent") is None

    def test_update_entity(self):
        self.graph.add_entity("x", "X v1", "concept")
        self.graph.add_entity("x", "X v2", "tool")
        entity = self.graph.get_entity("x")
        assert entity["label"] == "X v2"
        assert entity["entity_type"] == "tool"

    def test_list_entities(self):
        self.graph.add_entity("a", "A", "concept")
        self.graph.add_entity("b", "B", "tool")
        self.graph.add_entity("c", "C", "concept")

        all_entities = self.graph.list_entities()
        assert len(all_entities) == 3

        concepts = self.graph.list_entities(entity_type="concept")
        assert len(concepts) == 2

    def test_entity_count(self):
        self.graph.add_entity("a", "A", "concept")
        self.graph.add_entity("b", "B", "tool")
        assert self.graph.entity_count == 2


class TestFactOperations:
    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "The User", "person")
        self.graph.add_entity("rag", "RAG", "concept")
        self.graph.add_entity("neo4j", "Neo4j", "tool")

    def test_add_fact_entity_object(self):
        fact_id = self.graph.add_fact(
            "user", "works_on",
            object_id="rag",
            source_episode_id="ep1",
        )
        assert isinstance(fact_id, str) and len(fact_id) > 0

        fact = self.graph.get_fact(fact_id)
        assert fact is not None
        assert fact["subject"] == "user"
        assert fact["predicate"] == "works_on"
        assert fact["object"] == "rag"

    def test_add_fact_literal_object(self):
        fact_id = self.graph.add_fact(
            "user", "name",
            object_literal="Ayush",
        )
        fact = self.graph.get_fact(fact_id)
        assert fact is not None
        assert fact["object_literal"] == "Ayush"
        assert fact["object"].startswith("_literal:")

    def test_add_fact_requires_exactly_one_object(self):
        import pytest
        with pytest.raises(ValueError):
            self.graph.add_fact("user", "works_on")  # neither
        with pytest.raises(ValueError):
            self.graph.add_fact("user", "works_on", object_id="rag", object_literal="RAG")  # both

    def test_fact_with_temporal_fields(self):
        fact_id = self.graph.add_fact(
            "user", "believes",
            object_literal="bi-temporal modeling is important",
            valid_from="2026-01-01",
            valid_to=None,
            recorded_at="2026-08-20T12:00:00Z",
            confidence=0.9,
        )
        fact = self.graph.get_fact(fact_id)
        assert fact["valid_from"] == "2026-01-01"
        assert fact["valid_to"] is None
        assert fact["recorded_at"] == "2026-08-20T12:00:00Z"
        assert fact["confidence"] == 0.9

    def test_fact_count(self):
        self.graph.add_fact("user", "works_on", object_id="rag")
        self.graph.add_fact("user", "uses", object_id="neo4j")
        assert self.graph.fact_count == 2

    def test_get_nonexistent_fact(self):
        assert self.graph.get_fact("nonexistent") is None

    def test_multiple_facts_same_entities(self):
        """Multiple facts can exist between the same entities (MultiDiGraph)."""
        self.graph.add_fact("user", "works_on", object_id="rag")
        self.graph.add_fact("user", "believes_in", object_id="rag")
        assert self.graph.fact_count == 2


class TestPointInTimeQueries:
    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "The User", "person")
        self.graph.add_entity("concept_a", "Concept A", "concept")
        self.graph.add_entity("concept_b", "Concept B", "concept")

        # Fact 1: user believed A from Jan to Jun 2026
        self.graph.add_fact(
            "user", "believes",
            object_id="concept_a",
            valid_from="2026-01-01",
            valid_to="2026-06-30",
            recorded_at="2026-01-15T00:00:00Z",
        )

        # Fact 2: user believed B from May 2026 onward
        self.graph.add_fact(
            "user", "believes",
            object_id="concept_b",
            valid_from="2026-05-01",
            valid_to=None,
            recorded_at="2026-05-10T00:00:00Z",
        )

        # Fact 3: user works_on rag (no temporal bounds)
        self.graph.add_fact(
            "user", "works_on",
            object_id="concept_a",
            valid_from=None,
            valid_to=None,
        )

    def test_query_as_of_march(self):
        """In March, only fact1 should be valid."""
        facts = self.graph.query_as_of("2026-03-15")
        preds = {f["predicate"]: f["object"] for f in facts}
        # fact1 (believes concept_a) should be valid
        believe_facts = [f for f in facts if f["predicate"] == "believes"]
        assert len(believe_facts) == 1
        assert believe_facts[0]["object"] == "concept_a"

    def test_query_as_of_july(self):
        """In July, fact1 has ended, only fact2 is valid."""
        facts = self.graph.query_as_of("2026-07-15")
        believe_facts = [f for f in facts if f["predicate"] == "believes"]
        assert len(believe_facts) == 1
        assert believe_facts[0]["object"] == "concept_b"

    def test_query_as_of_may(self):
        """In May, both fact1 and fact2 overlap."""
        facts = self.graph.query_as_of("2026-05-15")
        believe_facts = [f for f in facts if f["predicate"] == "believes"]
        assert len(believe_facts) == 2

    def test_query_with_entity_filter(self):
        facts = self.graph.query_as_of("2026-03-15", entity="user")
        assert all(f["subject"] == "user" or f["object"] == "user" for f in facts)

    def test_query_with_predicate_filter(self):
        facts = self.graph.query_as_of("2026-03-15", predicate="works_on")
        assert all(f["predicate"] == "works_on" for f in facts)

    def test_query_superseded_before_supersession(self):
        """A superseded fact appears in queries BEFORE the supersession happened."""
        self.graph.add_fact(
            "user", "status",
            object_literal="active",
            valid_from="2026-01-01",
        )
        result = self.graph.supersede_and_add(
            "user", "status",
            object_literal="inactive",
            valid_from="2026-06-01",
        )
        # Supersession recorded in Aug 2026. Query July → old fact still visible.
        facts_july = self.graph.query_as_of("2026-07-01", predicate="status")
        assert len(facts_july) == 2  # both active: old (not yet superseded in July) + new

        # Query in Sep (after supersession recorded) → only new fact
        facts_sep = self.graph.query_as_of("2026-09-01", predicate="status")
        assert len(facts_sep) == 1
        assert facts_sep[0]["object_literal"] == "inactive"


class TestSupersedingAndContradictions:
    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "The User", "person")
        self.graph.add_entity("tool_x", "Tool X", "tool")
        self.graph.add_entity("tool_y", "Tool Y", "tool")

    def test_supersede_and_add(self):
        """New fact supersedes old one with same subject+predicate but different object."""
        # Old belief
        self.graph.add_fact(
            "user", "prefers",
            object_id="tool_x",
            valid_from="2026-01-01",
        )

        # New belief supersedes old
        result = self.graph.supersede_and_add(
            "user", "prefers",
            object_id="tool_y",
            valid_from="2026-06-01",
        )

        assert len(result["superseded"]) == 1
        old_fact = self.graph.get_fact(result["superseded"][0])
        assert old_fact["superseded_by"] == result["new_fact_id"]
        assert old_fact["valid_to"] is not None  # closed

    def test_no_contradiction_same_object(self):
        """Same subject+predicate+object is NOT a contradiction."""
        self.graph.add_fact("user", "works_on", object_id="tool_x")
        result = self.graph.supersede_and_add(
            "user", "works_on",
            object_id="tool_x",
        )
        assert len(result["superseded"]) == 0

    def test_no_contradiction_different_predicate(self):
        """Different predicates don't contradict."""
        self.graph.add_fact("user", "prefers", object_id="tool_x")
        result = self.graph.supersede_and_add(
            "user", "uses",
            object_id="tool_y",
        )
        assert len(result["superseded"]) == 0

    def test_contradiction_detection(self):
        """Direct contradiction detection without superseding."""
        self.graph.add_fact(
            "user", "believes",
            object_literal="X is true",
            valid_from="2026-01-01",
            valid_to="2026-12-31",
        )

        contradictions = self.graph.find_contradictions(
            "user", "believes", "X is false",
            valid_from="2026-06-01",
        )
        assert len(contradictions) == 1

    def test_no_contradiction_non_overlapping(self):
        """Facts with non-overlapping windows don't contradict."""
        self.graph.add_fact(
            "user", "believes",
            object_literal="X is true",
            valid_from="2026-01-01",
            valid_to="2026-06-30",
        )

        contradictions = self.graph.find_contradictions(
            "user", "believes", "X is false",
            valid_from="2026-07-01",
            valid_to="2026-12-31",
        )
        assert len(contradictions) == 0

    def test_superseded_fact_not_in_contradictions(self):
        """Already-superseded facts don't show up as contradictions."""
        old_id = self.graph.add_fact(
            "user", "believes",
            object_literal="old belief",
            valid_from="2026-01-01",
        )
        new_result = self.graph.supersede_and_add(
            "user", "believes",
            object_literal="new belief",
            valid_from="2026-06-01",
        )

        # Now try to find contradictions for another different belief
        contradictions = self.graph.find_contradictions(
            "user", "believes", "third belief",
            valid_from="2026-06-01",
        )
        # Only the new belief should contradict, not the old superseded one
        assert len(contradictions) == 1
        assert contradictions[0]["fact_id"] == new_result["new_fact_id"]


class TestGraphTraversal:
    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "User", "person")
        self.graph.add_entity("project_a", "Project A", "concept")
        self.graph.add_entity("tool_x", "Tool X", "tool")
        self.graph.add_entity("library_y", "Library Y", "tool")

        self.graph.add_fact("user", "works_on", object_id="project_a")
        self.graph.add_fact("project_a", "uses", object_id="tool_x")
        self.graph.add_fact("tool_x", "depends_on", object_id="library_y")

    def test_one_hop(self):
        facts = self.graph.neighbors("user", hops=1)
        # user → project_a (1 hop)
        objects = {f["object"] for f in facts}
        assert "project_a" in objects
        assert "tool_x" not in objects  # 2 hops away

    def test_two_hops(self):
        facts = self.graph.neighbors("user", hops=2)
        objects = {f["object"] for f in facts}
        assert "project_a" in objects
        assert "tool_x" in objects
        assert "library_y" not in objects  # 3 hops

    def test_three_hops(self):
        facts = self.graph.neighbors("user", hops=3)
        objects = {f["object"] for f in facts}
        assert "library_y" in objects

    def test_traversal_respects_validity(self):
        """Traversal filters by time."""
        self.graph.add_entity("concept_z", "Concept Z", "concept")
        self.graph.add_fact(
            "user", "explores",
            object_id="concept_z",
            valid_from="2026-06-01",
            valid_to="2026-06-30",
        )

        # At March, concept_z should not appear
        facts_march = self.graph.neighbors("user", hops=1, valid_as_of="2026-03-15")
        objects_march = {f["object"] for f in facts_march}
        assert "concept_z" not in objects_march

        # At June, concept_z should appear
        facts_june = self.graph.neighbors("user", hops=1, valid_as_of="2026-06-15")
        objects_june = {f["object"] for f in facts_june}
        assert "concept_z" in objects_june


class TestStatsAndSerialization:
    def test_stats(self):
        graph = TemporalGraph()
        graph.add_entity("a", "A", "concept")
        graph.add_entity("b", "B", "tool")
        graph.add_fact("a", "uses", object_id="b")

        stats = graph.stats()
        assert stats["entities"] == 2
        assert stats["facts"] == 1
        assert stats["active_facts"] == 1

    def test_save_and_load(self):
        graph = TemporalGraph()
        graph.add_entity("test", "Test", "concept")
        graph.add_fact("test", "has_property", object_literal="value")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        graph.save(path)

        graph2 = TemporalGraph()
        graph2.load(path)

        assert graph2.entity_count == 1
        assert graph2.fact_count == 1
        assert graph2.has_entity("test")

        Path(path).unlink()
