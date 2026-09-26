"""Query API routes.

POST /query        — hybrid search over episodic + semantic memory
                     (dense + BM25 + graph traversal + purpose-aware document boost)
POST /query/answer — retrieval → privacy-tiered LLM routing → cited answer
                     with short-term conversation memory (06 §3)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.answer import (
    LLMCallError,
    LLMUnavailableError,
    generate_answer,
    route_llm,
    sessions,
)
from backend.api.routes_ingest import get_pipeline
from backend.memory import audit
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
    boost_documents: bool = True  # Phase 7: purpose-aware document boost


class QueryResult(BaseModel):
    id: str
    text: str
    score: float
    source: str  # "dense", "bm25", "graph", "document+purpose", combinations
    metadata: dict


class QueryResponse(BaseModel):
    results: list[QueryResult]
    total: int
    sources_used: list[str]  # which sources contributed results


class AnswerRequest(BaseModel):
    question: str
    session_id: str | None = None  # pass back the previous turn's id to continue
    top_k: int = 8
    valid_as_of: str | None = None


class Citation(BaseModel):
    index: int  # 1-based, matches the [n] markers in the answer
    id: str
    source: str
    score: float
    text: str


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    route: dict  # provider/model/reason — see RouteDecision.as_dict()
    session_id: str  # continue the conversation by sending this back
    results_total: int


def _run_search(
    query: str,
    *,
    top_k: int,
    dense_weight: float | None = None,
    bm25_weight: float | None = None,
    graph_weight: float | None = None,
    graph_hops: int | None = None,
    valid_as_of: str | None = None,
    boost_documents: bool = True,
):
    pipeline = get_pipeline()
    retriever = HybridRetriever(
        episodic_store=pipeline.store,
        bm25_index=pipeline.bm25,
        graph=pipeline.graph,
    )
    return retriever.search(
        query,
        top_k=top_k,
        dense_weight=dense_weight,
        bm25_weight=bm25_weight,
        graph_weight=graph_weight,
        graph_hops=graph_hops,
        valid_as_of=valid_as_of,
        boost_documents=boost_documents,
    )


@router.post("", response_model=QueryResponse)
def query_memory(req: QueryRequest):
    """Hybrid search: dense + BM25 + graph traversal.

    The graph source adds structured knowledge that plain RAG misses:
    entity relationships, temporal context, and connected facts.
    Purpose-matched Document nodes are boosted ahead of the fused list
    when the question is about *which file*, not *what does it say*.
    """
    results = _run_search(
        req.query,
        top_k=req.top_k,
        dense_weight=req.dense_weight,
        bm25_weight=req.bm25_weight,
        graph_weight=req.graph_weight,
        graph_hops=req.graph_hops,
        valid_as_of=req.valid_as_of,
        boost_documents=req.boost_documents,
    )

    # Collect which sources contributed
    sources_used: set[str] = set()
    for r in results:
        for src in r.source.split("+"):
            sources_used.add(src)

    audit.record("query", query_text=req.query, detail=f"{len(results)} results")

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


@router.post("/answer", response_model=AnswerResponse)
def answer_question(req: AnswerRequest):
    """Grounded answer with privacy-tiered model routing.

    Pipeline: hybrid retrieve → route by evidence sensitivity (06 §3) →
    synthesize a cited answer → remember the turn for follow-ups.
    """
    results = _run_search(req.question, top_k=req.top_k, valid_as_of=req.valid_as_of)

    session_id, history = sessions.get_or_create(req.session_id)

    if not results:
        # No evidence: skip the model entirely — cheaper and never invents.
        answer = (
            "I couldn't find anything relevant in your memory for that question."
        )
        route = {"provider": "none", "model": "", "reason": "no_results",
                 "sensitive": False, "fallback_from": None}
        citations: list[Citation] = []
    else:
        try:
            decision = route_llm(req.question, results)
        except LLMUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            generated = generate_answer(req.question, results, history, decision)
        except LLMCallError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        answer = generated.answer
        route = decision.as_dict()
        citations = [
            Citation(
                index=i,
                id=r.id,
                source=r.source,
                score=r.score,
                text=r.text,
            )
            for i, r in enumerate(results, start=1)
        ]

    sessions.append(session_id, req.question, answer)
    audit.record(
        "query_answer",
        query_text=req.question,
        detail=f"provider={route['provider']} citations={len(citations)}",
    )

    return AnswerResponse(
        answer=answer,
        citations=citations,
        route=route,
        session_id=session_id,
        results_total=len(results),
    )
