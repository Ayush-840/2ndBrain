"""Text chunking for the enrichment pipeline.

Splits long captures into overlapping chunks suitable for embedding.
Uses a simple character-level sliding window — keeps things predictable
and debuggable.  Can be swapped for a semantic chunker later without
touching the rest of the pipeline.
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    chunk_index: int
    source_capture_id: str
    start_offset: int  # character offset within the original capture
    end_offset: int


def chunk_text(
    text: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    capture_id: str = "",
    min_chunk_size: int = 50,
) -> list[Chunk]:
    """Split `text` into overlapping chunks.

    Args:
        text: The input text to chunk.
        chunk_size: Maximum number of characters per chunk.
        chunk_overlap: Number of overlapping characters between adjacent chunks.
        capture_id: ID of the parent capture (carried into each Chunk).
        min_chunk_size: Discard chunks shorter than this (avoids tiny slivers).

    Returns:
        List of Chunk objects with offset metadata.
    """
    if not text or not text.strip():
        return []

    chunks: list[Chunk] = []
    start = 0
    idx = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at the last sentence boundary or whitespace before `end`
        if end < len(text):
            # Look for sentence endings
            for sep in ("\n\n", "\n", ". ", "! ", "? ", " "):
                last_sep = text.rfind(sep, start, end)
                if last_sep > start:
                    end = last_sep + len(sep)
                    break

        chunk_text_str = text[start:end].strip()

        if len(chunk_text_str) >= min_chunk_size:
            chunks.append(
                Chunk(
                    text=chunk_text_str,
                    chunk_index=idx,
                    source_capture_id=capture_id,
                    start_offset=start,
                    end_offset=end,
                )
            )
            idx += 1

        # Advance by (chunk_size - overlap) to create the sliding window
        start = end - chunk_overlap
        if start >= end:
            break  # safety: prevent infinite loop

    return chunks
