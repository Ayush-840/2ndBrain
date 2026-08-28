"""Tests for the evaluation harness."""

import tempfile
from pathlib import Path

from backend.eval.golden_set import GoldenQuery, get_golden_set, get_all_query_types, DEFAULT_SEEDS
from backend.eval.scorer import (
    QueryScore,
    score_entity_recall,
    score_predicate_recall,
    score_answer_relevance,
    score_query,
    aggregate_results,
    save_results,
    EvalResult,
)
from backend.eval.runner import seed_graph, extract_entities_from_results
from backend.memory.graph import TemporalGraph


class TestGoldenSet:
    def test_golden_set_not_empty(self):
        queries = get_golden_set()
        assert len(queries) > 0

    def test_all_query_types_present(self):
        types = get_all_query_types()
        assert "single_hop" in types
        assert "multi_hop" in types
        assert "point_in_time" in types
        assert "contradiction" in types

    def test_filter_by_type(self):
        single = get_golden_set(query_type="single_hop")
        for q in single:
            assert q.query_type == "single_hop"

    def test_filter_by_difficulty(self):
        easy = get_golden_set(difficulty="easy")
        for q in easy:
            assert q.difficulty == "easy"

    def test_default_seeds_define_entities(self):
        entity_seeds = [s for s in DEFAULT_SEEDS if "entity" in s]
        assert len(entity_seeds) >= 10

    def test_default_seeds_define_facts(self):
        fact_seeds = [s for s in DEFAULT_SEEDS if "fact" in s]
        assert len(fact_seeds) >= 10


class TestSeedGraph:
    def test_seeds_entities(self):
        graph = TemporalGraph()
        seed_graph(graph)
        assert graph.entity_count >= 10
        assert graph.has_entity("user")
        assert graph.has_entity("rag")

    def test_seeds_facts(self):
        graph = TemporalGraph()
        seed_graph(graph)
        assert graph.fact_count >= 10

    def test_temporal_facts_present(self):
        graph = TemporalGraph()
        seed_graph(graph)
        facts = graph.query_all_facts(include_superseded=True)
        temporal = [f for f in facts if f.get("valid_from")]
        assert len(temporal) >= 5


class TestScorer:
    def test_entity_recall_all_found(self):
        recall, matched, missed = score_entity_recall(
            ["user", "rag"], ["user", "rag"], [], ""
        )
        assert recall == 1.0
        assert len(missed) == 0

    def test_entity_recall_partial(self):
        recall, matched, missed = score_entity_recall(
            ["user", "rag", "neo4j"], ["user", "rag"], [], ""
        )
        assert recall < 1.0
        assert "neo4j" in missed

    def test_entity_recall_in_text(self):
        recall, matched, missed = score_entity_recall(
            ["neo4j"], [], [], "The system uses Neo4j for graph storage."
        )
        assert recall == 1.0

    def test_predicate_recall(self):
        recall, matched, missed = score_predicate_recall(
            ["works_on", "uses"], ["works_on", "uses"], ""
        )
        assert recall == 1.0

    def test_answer_relevance(self):
        relevance, matches, miss = score_answer_relevance(
            ["networkx", "chromadb"], ["Uses NetworkX and ChromaDB"]
        )
        assert relevance == 1.0

    def test_answer_relevance_partial(self):
        relevance, matches, miss = score_answer_relevance(
            ["networkx", "neo4j"], ["Uses NetworkX"]
        )
        assert relevance == 0.5
        assert "neo4j" in miss

    def test_empty_expectations(self):
        recall, _, _ = score_entity_recall([], [], [], "")
        assert recall == 1.0

    def test_overall_score_computed(self):
        score = QueryScore(
            query="test",
            query_type="single_hop",
            difficulty="easy",
            entity_recall=1.0,
            predicate_recall=1.0,
            answer_relevance=0.5,
        )
        overall = score.compute_overall()
        assert 0.0 <= overall <= 1.0
        assert overall > 0.5  # mostly correct


class TestAggregateResults:
    def test_aggregate(self):
        scores = [
            QueryScore(query="q1", query_type="single_hop", difficulty="easy", overall=0.8),
            QueryScore(query="q2", query_type="multi_hop", difficulty="medium", overall=0.6),
            QueryScore(query="q3", query_type="single_hop", difficulty="easy", overall=0.4),
        ]
        result = aggregate_results(scores)
        assert result.total_queries == 3
        assert result.avg_overall > 0.0
        assert "single_hop" in result.avg_by_type
        assert result.pass_rate > 0.0

    def test_empty_aggregate(self):
        result = aggregate_results([])
        assert result.total_queries == 0


class TestSaveResults:
    def test_save_and_load(self):
        result = EvalResult(
            timestamp="2026-08-28",
            total_queries=1,
            avg_overall=0.75,
            pass_rate=1.0,
            summary="test summary",
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        save_results(result, path)
        content = Path(path).read_text()
        assert "2026-08-28" in content
        assert "test summary" in content
        Path(path).unlink()
