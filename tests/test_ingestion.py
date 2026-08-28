"""Tests for ingestion adapters."""

from pathlib import Path

from backend.ingestion.markdown import MarkdownAdapter
from backend.ingestion.pdf import PDFAdapter

SAMPLE_VAULT = Path("data/sample_vault")


class TestMarkdownAdapter:
    def setup_method(self):
        self.adapter = MarkdownAdapter()

    def test_ingest_single_file(self):
        filepath = SAMPLE_VAULT / "ai-memory.md"
        captures = self.adapter.ingest(str(filepath))

        assert len(captures) == 1
        capture = captures[0]
        assert capture.source_type == "markdown"
        assert "Episodic Memory" in capture.content
        assert capture.metadata["filename"] == "ai-memory.md"
        assert "tags" in capture.metadata

    def test_ingest_directory(self):
        captures = self.adapter.ingest(str(SAMPLE_VAULT))

        assert len(captures) >= 2
        filenames = {c.metadata["filename"] for c in captures}
        assert "ai-memory.md" in filenames
        assert "temporal-databases.md" in filenames

    def test_frontmatter_extracted(self):
        captures = self.adapter.ingest(str(SAMPLE_VAULT / "ai-memory.md"))
        meta = captures[0].metadata
        assert meta["tags"] == ["ai", "memory", "rag", "knowledge-graph"]
        assert meta["title"] == "AI Memory Systems"

    def test_nonexistent_path_raises(self):
        import pytest

        with pytest.raises(FileNotFoundError):
            self.adapter.ingest("/nonexistent/path.md")


class TestPDFAdapter:
    def setup_method(self):
        self.adapter = PDFAdapter()

    def test_nonexistent_path_raises(self):
        import pytest

        with pytest.raises(FileNotFoundError):
            self.adapter.ingest("/nonexistent/file.pdf")
