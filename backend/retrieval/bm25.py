"""BM25 lexical search wrapper.

Maintains an in-memory BM25 index that stays in sync with the episodic
store.  In Phase 1 this is a lightweight layer over rank_bm25; later
it can be backed by Elasticsearch or similar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercasing tokenizer.  Good enough for BM25."""
    return re.findall(r"\b\w+\b", text.lower())


@dataclass
class BM25Index:
    """A BM25 index over episodic chunks."""

    _documents: list[str] = field(default_factory=list)
    _doc_ids: list[str] = field(default_factory=list)
    _metadatas: list[dict] = field(default_factory=list)
    _bm25: BM25Okapi | None = field(default=None, init=False, repr=False)

    def add(
        self,
        doc_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        self._documents.append(text)
        self._doc_ids.append(doc_id)
        self._metadatas.append(metadata or {})
        self._bm25 = None  # invalidate

    def add_batch(
        self,
        doc_ids: list[str],
        texts: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        metadatas = metadatas or [{} for _ in doc_ids]
        self._documents.extend(texts)
        self._doc_ids.extend(doc_ids)
        self._metadatas.extend(metadatas)
        self._bm25 = None

    def _rebuild(self) -> None:
        if self._documents:
            tokenized = [_tokenize(d) for d in self._documents]
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = BM25Okapi([])

    @property
    def count(self) -> int:
        return len(self._documents)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Return the top-k documents matching `query` by BM25 score."""
        if not self._documents:
            return []

        if self._bm25 is None:
            self._rebuild()

        tokenized_query = _tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Pair scores with indices and sort descending
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        results: list[dict] = []
        for idx, score in ranked:
            if score <= 0:
                break
            results.append(
                {
                    "id": self._doc_ids[idx],
                    "text": self._documents[idx],
                    "bm25_score": float(score),
                    "metadata": self._metadatas[idx],
                }
            )
        return results

    def clear(self) -> None:
        self._documents.clear()
        self._doc_ids.clear()
        self._metadatas.clear()
        self._bm25 = None
