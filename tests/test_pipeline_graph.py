"""Integration tests for the pipeline with graph storage.

Tests the full flow: ingest → extract (mocked) → store in graph → query.
"""

from unittest.mock import MagicMock, patch

from backend.enrichment.extractor import ExtractionResult, ExtractedEntity, ExtractedFact
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.pipeline import Pipeline
from backend.retrieval.bm25 import BM25Index


def _mock_extraction_result() -> ExtractionResult:
    """Return a canned extraction result for testing."""
    return ExtractionResult(
        entities=[
            ExtractedEntity("user", "The User", "person"),
            ExtractedEntity("rag", "RAG", "concept"),
            ExtractedEntity("graph_db", "Graph Database", "concept"),
        ],
        facts=[
            ExtractedFact(
                subject="user",
                predicate="works_on",
                object_id="rag",
                confidence=0.95,
            ),
            ExtractedFact(
                subject="user",
                predicate="believes",
                object_literal="graph databases are better than vector stores",
                valid_from="2026-08-20",
                confidence=0.8,
            ),
            ExtractedFact(
                subject="rag",
                predicate="uses",
                object_id="graph_db",
                confidence=0.7,
            ),
        ],
    )


class TestPipelineWithGraph:
    def setup_method(self):
        self.pipeline = Pipeline(
            episodic_store=EpisodicStore(persist_dir="/tmp/test_episodic"),
            bm25_index=BM25Index(),
            graph=TemporalGraph(),
        )
        self.pipeline.store.reset()

    def test_ingest_with_extraction(self):
        """Test that ingestion populates both episodic store and graph."""
        # Mock the extractor directly on the pipeline instance
        self.pipeline._extractor = MagicMock()
        self.pipeline._extractor.extract.return_value = _mock_extraction_result()

        result = self.pipeline.ingest_source(
            "data/sample_vault", "markdown", extract=True
        )

        assert result["num_captures"] >= 2
        assert result["num_chunks"] > 0
        assert result["entities_extracted"] > 0
        assert result["facts_extracted"] > 0

        # Verify graph was populated
        graph_stats = self.pipeline.graph.stats()
        assert graph_stats["entities"] > 0
        assert graph_stats["facts"] > 0

    def test_extract_and_store(self):
        """Test on-demand extraction from arbitrary text."""
        self.pipeline._extractor = MagicMock()
        self.pipeline._extractor.extract.return_value = _mock_extraction_result()

        result = self.pipeline.extract_and_store(
            "The user works on RAG and believes graph databases are superior.",
            source_context="test_note.md",
        )

        assert result["entities_added"] == 3
        assert result["facts_added"] == 3
        assert result["graph_stats"]["entities"] == 3
        assert result["graph_stats"]["facts"] == 3

    def test_graph_queries_after_extraction(self):
        """Test that graph queries work after extraction."""
        self.pipeline._extractor = MagicMock()
        self.pipeline._extractor.extract.return_value = _mock_extraction_result()

        self.pipeline.extract_and_store("test text")

        # Point-in-time query
        facts = self.pipeline.graph.query_as_of("2026-08-25")
        assert len(facts) > 0

        # Entity neighbors
        neighbors = self.pipeline.graph.neighbors("user", hops=1)
        assert len(neighbors) > 0

    def test_contradiction_detection_after_extraction(self):
        """Test that contradictions are detected when re-extracting."""
        self.pipeline._extractor = MagicMock()

        # First extraction: user believes X
        first_result = ExtractionResult(
            entities=[ExtractedEntity("user", "User", "person")],
            facts=[
                ExtractedFact(
                    subject="user",
                    predicate="believes",
                    object_literal="vector stores are best",
                    valid_from="2026-01-01",
                )
            ],
        )
        self.pipeline._extractor.extract.return_value = first_result
        self.pipeline.extract_and_store("first note")

        # Second extraction: user now believes Y (contradicts X)
        second_result = ExtractionResult(
            entities=[ExtractedEntity("user", "User", "person")],
            facts=[
                ExtractedFact(
                    subject="user",
                    predicate="believes",
                    object_literal="graph databases are best",
                    valid_from="2026-06-01",
                )
            ],
        )
        self.pipeline._extractor.extract.return_value = second_result
        outcome = self.pipeline.extract_and_store("second note")

        # The old fact should have been superseded
        assert outcome["contradictions_found"] > 0

        # Query at different times
        facts_jan = self.pipeline.graph.query_as_of("2026-03-01", predicate="believes")
        facts_jul = self.pipeline.graph.query_as_of("2026-07-01", predicate="believes")

        # In Jan, only the first belief is valid
        assert any("vector" in (f.get("object_literal") or "") for f in facts_jan)
        # In Jul, only the second belief is valid
        assert any("graph" in (f.get("object_literal") or "") for f in facts_jul)

    def test_episodic_and_graph_cohabit(self):
        """Both stores are populated from the same pipeline run."""
        self.pipeline._extractor = MagicMock()
        self.pipeline._extractor.extract.return_value = _mock_extraction_result()

        self.pipeline.ingest_source("data/sample_vault", "markdown", extract=True)

        # Episodic has chunks
        assert self.pipeline.store.count > 0

        # BM25 has indexed documents
        assert self.pipeline.bm25.count > 0

        # Graph has entities and facts
        stats = self.pipeline.graph.stats()
        assert stats["entities"] > 0
        assert stats["facts"] > 0
