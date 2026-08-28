"""Embedding wrapper using sentence-transformers.

Loads the model lazily (first call to embed) so importing this module
doesn't trigger a multi-hundred-MB download.  All embedding goes through
this single class, making it easy to swap models or add caching later.
"""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from backend.config import settings

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

_model: SentenceTransformer | None = None



def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts and return dense vectors.

    Args:
        texts: Non-empty list of strings.

    Returns:
        List of float vectors, one per input text.
    """
    if not texts:
        return []

    model = _get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]


def get_embedding_dim() -> int:
    """Return the dimensionality of the current embedding model."""
    return settings.embedding_dim
