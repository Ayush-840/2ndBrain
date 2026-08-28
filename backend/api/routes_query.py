"""Query API routes.

POST /query — hybrid search over episodic + semantic memory
              (dense + BM25 + graph traversal)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.routes_ingest import get_pipeline
from backend.retrieval.hybrid import HybridRetriever

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    dense_weight: float | None = None
    bm25_weight: float | None = None
    graph_weight: float | None = None
    graph_hops: int | None = None
    valid_as_of: str | None = None  # point-in-time graph query


class QueryResult(BaseModel):
    id: str
    text: str
    score: float
    source: str  # "dense", "bm25", "graph", "dense+graph", etc.
    metadata: dict


class QueryResponse(BaseModel):
    results: list[QueryResult]
    total: int
    sources_used: list[str]  # which sources contributed results


@router.post("", response_model=QueryResponse)
def query_memory(req: QueryRequest):
    """Hybrid search: dense + BM25 + graph traversal.

    The graph source adds structured knowledge that plain RAG misses:
    entity relationships, temporal context, and connected facts.
    """
    pipeline = get_pipeline()
    retriever = HybridRetriever(
        episodic_store=pipeline.store,
        bm25_index=pipeline.bm25,
        graph=pipeline.graph,
    )

    results = retriever.search(
        req.query,
        top_k=req.top_k,
        dense_weight=req.dense_weight,
        bm25_weight=req.bm25_weight,
        graph_weight=req.graph_weight,
        graph_hops=req.graph_hops,
        valid_as_of=req.valid_as_of,
    )



    # Collect which sources contributed
    sources_used: set[str] = set()
    for r in results:
        for src in r.source.split("+"):
            sources_used.add(src)

    return QueryResponse(
        results=[
            QueryResult(
                id=r.id,
                text=r.text,
                score=r.score,
                source=r.source,
                metadata=r.metadata,
            )
            for r in results
        ],
        total=len(results),
        sources_used=sorted(sources_used),
    )
