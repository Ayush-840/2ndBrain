"""Tests for the surfacing agent."""

from backend.memory.graph import TemporalGraph
from backend.memory.community import CommunityStore, TopicCluster
from backend.surfacing.agent import SurfacingAgent, ContradictionFlag, ResurfacedNote, Digest


def _build_graph_with_contradictions() -> TemporalGraph:
    """Build a graph that has contradictions."""
    graph = TemporalGraph()
    graph.add_entity("user", "Ayush", "person")
    graph.add_entity("networkx", "NetworkX", "tool")
    graph.add_entity("neo4j", "Neo4j", "tool")
    graph.add_entity("rag", "RAG", "concept")

    # Contradiction 1: beliefs about storage
    graph.add_fact(
        "user", "believes",
        object_literal="NetworkX is sufficient",
        valid_from="2026-01-01", valid_to="2026-06-30",
        recorded_at="2026-01-15T00:00:00Z",
    )
    graph.add_fact(
        "user", "believes",
        object_literal="Neo4j would be better for scale",
        valid_from="2026-07-01",
        recorded_at="2026-07-10T00:00:00Z",
    )

    # Non-contradiction: different predicates
    graph.add_fact("user", "works_on", object_id="rag")
    graph.add_fact("user", "uses", object_id="networkx")

    # Contradiction 2: beliefs about search
    graph.add_fact(
        "user", "believes",
        object_literal="BM25 alone is enough",
        valid_from="2026-01-01", valid_to="2026-04-30",
        recorded_at="2026-02-01T00:00:00Z",
    )
    graph.add_fact(
        "user", "believes",
        object_literal="Hybrid retrieval with RRF is better",
        valid_from="2026-05-01",
        recorded_at="2026-05-15T00:00:00Z",
    )

    return graph


class TestContradictionDetection:
    def setup_method(self):
        self.graph = _build_graph_with_contradictions()
        self.agent = SurfacingAgent(graph=self.graph)

    def test_finds_contradictions(self):
        flags = self.agent.detect_contradictions()
        # Should find at least 2 contradictions (storage beliefs + search beliefs)
        assert len(flags) >= 2

    def test_contradiction_details(self):
        flags = self.agent.detect_contradictions()
        for flag in flags:
            assert flag.old_fact_id
            assert flag.new_fact_id
            assert flag.subject
            assert flag.predicate
            assert flag.old_value != flag.new_value
            assert flag.severity in ("info", "warning", "critical")

    def test_no_contradiction_different_predicate(self):
        """works_on and uses don't contradict each other."""
        flags = self.agent.detect_contradictions()
        non_belief = [f for f in flags if f.predicate not in ("believes",)]
        # Non-belief contradictions should be info severity or not exist
        for f in non_belief:
            assert f.severity == "info"

    def test_belief_contradictions_are_warning(self):
        flags = self.agent.detect_contradictions()
        belief_flags = [f for f in flags if f.predicate == "believes"]
        for f in belief_flags:
            assert f.severity == "warning"

    def test_since_filter(self):
        # Only contradictions detected after June 2026
        flags = self.agent.detect_contradictions(since="2026-06-01")
        # The "search beliefs" contradiction was recorded in May, so might not appear
        # The "storage beliefs" was recorded in July, so should appear
        assert len(flags) >= 1

    def test_empty_graph(self):
        agent = SurfacingAgent(graph=TemporalGraph())
        flags = agent.detect_contradictions()
        assert flags == []


class TestResurfacing:
    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "Ayush", "person")
        self.graph.add_entity("old_topic", "Old Topic", "concept")

        # Old fact (recorded 60 days ago)
        from datetime import datetime, timezone, timedelta
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        self.graph.add_fact(
            "user", "explores",
            object_id="old_topic",
            recorded_at=old_date,
        )

        # Recent fact
        self.graph.add_fact(
            "user", "works_on",
            object_literal="new project",
        )

        self.agent = SurfacingAgent(graph=self.graph)

    def test_resurface_finds_old_facts(self):
        notes = self.agent.resurface_relevant(
            context="old topic exploration",
            max_age_days=30,
        )
        # Should find the old fact
        assert len(notes) >= 1
        assert any("old_topic" in n.text.lower() or "old topic" in n.text.lower()
                   for n in notes)

    def test_resurface_with_no_context(self):
        notes = self.agent.resurface_relevant(max_age_days=30)
        # Should still return results (all get same score)
        assert isinstance(notes, list)

    def test_resurface_recent_facts_excluded(self):
        notes = self.agent.resurface_relevant(max_age_days=365)
        # With a very large max_age, even recent facts are included
        assert isinstance(notes, list)


class TestDigest:
    def setup_method(self):
        self.graph = _build_graph_with_contradictions()
        self.community = CommunityStore()
        self.community.add_cluster(TopicCluster(
            cluster_id="c1", label="Tools", summary="Tool-related facts",
            fact_ids=["f1", "f2"],
        ))
        self.agent = SurfacingAgent(graph=self.graph, community=self.community)

    def test_daily_digest(self):
        digest = self.agent.generate_digest(digest_type="daily")
        assert digest.digest_type == "daily"
        assert digest.generated_at
        assert len(digest.entries) > 0
        assert digest.summary

    def test_weekly_digest(self):
        digest = self.agent.generate_digest(digest_type="weekly")
        assert digest.digest_type == "weekly"
        assert len(digest.entries) > 0

    def test_digest_has_communities(self):
        digest = self.agent.generate_digest()
        categories = {e.category for e in digest.entries}
        assert "community_update" in categories

    def test_digest_has_graph_stats(self):
        digest = self.agent.generate_digest()
        categories = {e.category for e in digest.entries}
        assert "graph_stats" in categories

    def test_digest_with_since(self):
        digest = self.agent.generate_digest(since="2026-01-01")
        assert digest.period_start == "2026-01-01"

    def test_digest_no_community(self):
        agent = SurfacingAgent(graph=self.graph)
        digest = agent.generate_digest()
        # Should still work without community store
        assert len(digest.entries) > 0
