"""Community memory API routes.

POST /community/build    — cluster facts into topic communities
GET  /community/stats    — community store statistics
GET  /community/clusters — list all clusters
POST /community/search   — search clusters by query
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.routes_ingest import get_pipeline

router = APIRouter(prefix="/community", tags=["community"])


# ── Request / Response models ────────────────────────────────────────

class BuildRequest(BaseModel):
    max_clusters: int = 10
    summarize: bool = True


class ClusterResponse(BaseModel):
    cluster_id: str
    label: str
    summary: str
    fact_count: int
    entity_count: int
    created_at: str


class BuildResponse(BaseModel):
    num_clusters: int
    total_facts_in_clusters: int
    cluster_labels: list[str]


class StatsResponse(BaseModel):
    clusters: int
    facts_in_clusters: int
    avg_facts_per_cluster: float


class ClusterListResponse(BaseModel):
    clusters: list[ClusterResponse]
    total: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchResultResponse(BaseModel):
    cluster_id: str
    label: str
    summary: str
    score: float
    fact_ids: list[str]
    entity_ids: list[str]


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]
    total: int


# ── Routes ───────────────────────────────────────────────────────────

@router.post("/build", response_model=BuildResponse)
def build_communities(req: BuildRequest):
    """Cluster semantic facts into topic communities."""
    pipeline = get_pipeline()
    result = pipeline.build_communities(
        max_clusters=req.max_clusters,
        summarize=req.summarize,
    )
    return BuildResponse(**result)


@router.get("/stats", response_model=StatsResponse)
def community_stats():
    """Return community store statistics."""
    pipeline = get_pipeline()
    stats = pipeline.community.stats()
    return StatsResponse(**stats)


@router.get("/clusters", response_model=ClusterListResponse)
def list_clusters():
    """List all topic clusters."""
    pipeline = get_pipeline()
    clusters = pipeline.community.list_clusters()
    return ClusterListResponse(
        clusters=[
            ClusterResponse(
                cluster_id=c.cluster_id,
                label=c.label,
                summary=c.summary,
                fact_count=len(c.fact_ids),
                entity_count=len(c.entity_ids),
                created_at=c.created_at,
            )
            for c in clusters
        ],
        total=len(clusters),
    )


@router.post("/search", response_model=SearchResponse)
def search_clusters(req: SearchRequest):
    """Search clusters by query similarity."""
    pipeline = get_pipeline()
    results = pipeline.community.search_clusters(req.query, top_k=req.top_k)
    return SearchResponse(
        results=[
            SearchResultResponse(
                cluster_id=cluster.cluster_id,
                label=cluster.label,
                summary=cluster.summary,
                score=score,
                fact_ids=cluster.fact_ids,
                entity_ids=cluster.entity_ids,
            )
            for cluster, score in results
        ],
        total=len(results),
    )
