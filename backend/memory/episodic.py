"""Episodic memory store backed by ChromaDB.

This is the primary storage in Phase 1.  Each chunk gets:
  - its text content
  - a dense embedding (stored by ChromaDB)
  - metadata including capture_id, source path, timestamps, chunk offsets

ChromaDB handles both vector storage and metadata filtering, so we can
do "find chunks from this source" or "find chunks added since date X"
without maintaining a separate index.
"""

from datetime import datetime, timezone
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.config import settings
from backend.enrichment.chunker import Chunk


class EpisodicStore:
    """ChromaDB-backed store for episodic memory (raw captures + chunks)."""

    def __init__(self, persist_dir: str | None = None):
        persist_dir = persist_dir or str(settings.chroma_dir)
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    @property
    def collection(self):
        return self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def _collection(self):
        return self.collection


    @property
    def count(self) -> int:
        return self._collection.count()

    def add_chunk(
        self,
        chunk: Chunk,
        embedding: list[float],
        *,
        source_path: str = "",
        source_type: str = "",
        extra_metadata: dict | None = None,
    ) -> str:
        """Add a single chunk with its embedding. Returns the chunk's doc_id."""
        doc_id = uuid4().hex
        metadata = {
            "capture_id": chunk.source_capture_id,
            "chunk_index": chunk.chunk_index,
            "start_offset": chunk.start_offset,
            "end_offset": chunk.end_offset,
            "source_path": source_path,
            "source_type": source_type,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        self._collection.add(
            ids=[doc_id],
            documents=[chunk.text],
            embeddings=[embedding],
            metadatas=[metadata],
        )
        return doc_id

    def add_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        *,
        source_path: str = "",
        source_type: str = "",
        extra_metadata: dict | None = None,
    ) -> list[str]:
        """Bulk-add chunks.  All chunks share the same source metadata."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return []

        ids = [uuid4().hex for _ in chunks]
        now = datetime.now(timezone.utc).isoformat()

        metadatas = []
        for chunk in chunks:
            meta = {
                "capture_id": chunk.source_capture_id,
                "chunk_index": chunk.chunk_index,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
                "source_path": source_path,
                "source_type": source_type,
                "recorded_at": now,
            }
            if extra_metadata:
                meta.update(extra_metadata)
            metadatas.append(meta)

        self._collection.add(
            ids=ids,
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return ids

    def query(
        self,
        query_embedding: list[float],
        *,
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[dict]:
        """Nearest-neighbor search over stored chunks.

        Returns a list of dicts with keys: id, text, distance, metadata.
        """
        top_k = top_k or settings.top_k
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "distances", "metadatas"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        items: list[dict] = []
        for i in range(len(results["ids"][0])):
            items.append(
                {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i],
                }
            )
        return items

    def iter_chunks(self):
        """Yield (chunk_id, text) for every stored chunk (used to rebuild BM25)."""
        data = self.collection.get(include=["documents"])
        for chunk_id, text in zip(data.get("ids") or [], data.get("documents") or []):
            if chunk_id and text:
                yield chunk_id, text

    def get_by_capture(self, capture_id: str, limit: int = 3) -> list[dict]:
        """Return chunks belonging to one capture (e.g. one WhatsApp document).

        Used by purpose-aware retrieval to pull a whole document back rather
        than whichever of its chunks happened to rank highest.
        """
        if not capture_id:
            return []
        try:
            results = self._collection.get(
                where={"capture_id": capture_id},
                limit=limit,
                include=["documents", "metadatas"],
            )
        except Exception:  # noqa: BLE001 — a filter Chroma dislikes must not 500 a query
            return []

        items: list[dict] = []
        for i, doc_id in enumerate(results.get("ids") or []):
            metadatas = results.get("metadatas") or []
            documents = results.get("documents") or []
            items.append(
                {
                    "id": doc_id,
                    "text": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                }
            )
        items.sort(key=lambda it: (it["metadata"] or {}).get("chunk_index", 0))
        return items

    def delete_source(self, source_path: str) -> int:
        """Delete all chunks from a specific source.  Returns count deleted."""
        before = self.count
        self._collection.delete(where={"source_path": source_path})
        return before - self.count

    def reset(self) -> None:
        """Delete the entire collection and recreate it."""
        try:
            self._client.delete_collection(settings.chroma_collection)
        except Exception:
            pass  # collection may not exist yet
        # Re-create via get_or_create — the @property will pick it up
        self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
