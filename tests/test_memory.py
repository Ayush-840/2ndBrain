"""Tests for memory stores."""

import tempfile
from pathlib import Path

from backend.enrichment.chunker import Chunk
from backend.memory.episodic import EpisodicStore
from backend.retrieval.bm25 import BM25Index


class TestEpisodicStore:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.store = EpisodicStore(persist_dir=self._tmpdir)

    def test_add_and_count(self):
        chunk = Chunk(
            text="Test chunk about AI memory",
            chunk_index=0,
            source_capture_id="cap1",
            start_offset=0,
            end_offset=100,
        )
        embedding = [0.1] * 384  # dummy embedding

        doc_id = self.store.add_chunk(chunk, embedding, source_path="/test.md")
        assert self.store.count == 1
        assert isinstance(doc_id, str) and len(doc_id) > 0

    def test_add_bulk(self):
        chunks = [
            Chunk(text=f"Chunk {i}", chunk_index=i, source_capture_id="cap1", start_offset=i * 10, end_offset=(i + 1) * 10)
            for i in range(5)
        ]
        embeddings = [[0.1] * 384 for _ in range(5)]

        doc_ids = self.store.add_chunks(chunks, embeddings, source_path="/bulk.md")
        assert len(doc_ids) == 5
        assert self.store.count == 5

    def test_query_returns_results(self):
        chunk = Chunk(
            text="Bi-temporal knowledge graphs track two timelines",
            chunk_index=0,
            source_capture_id="cap1",
            start_offset=0,
            end_offset=100,
        )
        embedding = [0.1] * 384
        self.store.add_chunk(chunk, embedding, source_path="/test.md")

        # Query with a similar embedding
        results = self.store.query(embedding, top_k=5)
        assert len(results) >= 1
        assert results[0]["text"] == chunk.text
        assert "metadata" in results[0]

    def test_delete_source(self):
        chunks = [
            Chunk(text=f"From source A {i}", chunk_index=i, source_capture_id="cap1", start_offset=0, end_offset=10)
            for i in range(3)
        ]
        embeddings = [[0.1] * 384 for _ in range(3)]
        self.store.add_chunks(chunks, embeddings, source_path="/source_a.md")

        chunks_b = [
            Chunk(text=f"From source B {i}", chunk_index=i, source_capture_id="cap2", start_offset=0, end_offset=10)
            for i in range(2)
        ]
        embeddings_b = [[0.2] * 384 for _ in range(2)]
        self.store.add_chunks(chunks_b, embeddings_b, source_path="/source_b.md")

        assert self.store.count == 5
        deleted = self.store.delete_source("/source_a.md")
        assert deleted == 3
        assert self.store.count == 2

    def test_reset(self):
        chunk = Chunk(text="Temporary", chunk_index=0, source_capture_id="cap1", start_offset=0, end_offset=10)
        self.store.add_chunk(chunk, [0.1] * 384, source_path="/tmp.md")
        assert self.store.count == 1

        self.store.reset()
        assert self.store.count == 0


class TestBM25Index:
    def setup_method(self):
        self.index = BM25Index()

    def test_add_and_search(self):
        self.index.add("doc1", "Machine learning models require training data")
        self.index.add("doc2", "Graph databases store entities and relationships")
        self.index.add("doc3", "Vector embeddings capture semantic similarity")

        results = self.index.search("machine learning", top_k=2)
        assert len(results) >= 1
        assert results[0]["id"] == "doc1"

    def test_add_batch(self):
        ids = ["d1", "d2", "d3"]
        texts = [
            "Natural language processing with transformers",
            "Computer vision using convolutional networks",
            "Reinforcement learning for game playing",
        ]
        self.index.add_batch(ids, texts)
        assert self.index.count == 3

    def test_empty_index(self):
        results = self.index.search("anything", top_k=5)
        assert results == []

    def test_clear(self):
        self.index.add("d1", "test document")
        assert self.index.count == 1
        self.index.clear()
        assert self.index.count == 0
