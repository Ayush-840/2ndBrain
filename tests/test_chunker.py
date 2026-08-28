"""Tests for text chunking."""

from backend.enrichment.chunker import chunk_text


class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "Hello world. This is a short note that is definitely longer than fifty characters so it passes the filter."
        chunks = chunk_text(text, chunk_size=512, min_chunk_size=50)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].start_offset == 0

    def test_long_text_produces_multiple_chunks(self):
        # 1000 chars, chunk_size=300 → should produce several chunks
        text = "word " * 200  # ~1000 chars
        chunks = chunk_text(text, chunk_size=300, chunk_overlap=50, min_chunk_size=10)
        assert len(chunks) > 1

    def test_overlap_prevents_gaps(self):
        # With overlap, content between chunks should appear in at least one chunk
        text = "A" * 100 + "B" * 100 + "C" * 100 + "D" * 100
        chunks = chunk_text(text, chunk_size=150, chunk_overlap=50, min_chunk_size=10)
        full_concat = "".join(c.text for c in chunks)
        assert "A" * 50 in full_concat
        assert "D" * 50 in full_concat

    def test_chunk_metadata(self):
        text = "x " * 300  # ~600 chars
        chunks = chunk_text(text, chunk_size=200, chunk_overlap=30, capture_id="cap123")
        for chunk in chunks:
            assert chunk.source_capture_id == "cap123"
            assert isinstance(chunk.start_offset, int)
            assert isinstance(chunk.end_offset, int)

    def test_min_chunk_size_filters_slivers(self):
        # Very long text with small min should filter tiny trailing chunks
        text = "A" * 100 + " " + "B" * 5  # The "B" part is tiny
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=10, min_chunk_size=5)
        for chunk in chunks:
            assert len(chunk.text) >= 5
