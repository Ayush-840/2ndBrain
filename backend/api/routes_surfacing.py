"""Surfacing agent API routes.

POST /surfing/contradictions  — detect contradictions
POST /surfing/resurface       — resurface stale-but-relevant notes
POST /surfing/digest          — generate a digest report
POST /surfing/run-daily       — trigger daily job manually
POST /surfing/run-weekly      — trigger weekly job manually
GET  /surfing/scheduler       — scheduler status
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.routes_ingest import get_pipeline

router = APIRouter(prefix="/surfing", tags=["surfacing"])


# ── Request / Response models ────────────────────────────────────────

class ContradictionFlagResponse(BaseModel):
    old_fact_id: str
    new_fact_id: str
    subject: str
    predicate: str
    old_value: str
    new_value: str
    old_valid_from: str | None = None
    new_valid_from: str | None = None
    detected_at: str
    severity: str


class ContradictionsResponse(BaseModel):
    contradictions: list[ContradictionFlagResponse]
    total: int


class ContradictionsRequest(BaseModel):
    since: str | None = None


class ResurfaceRequest(BaseModel):
    context: str = ""
    top_k: int = 10
    max_age_days: int = 30


class ResurfacedNoteResponse(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    object_value: str
    text: str
    relevance_score: float
    reason: str
    recorded_at: str | None = None


class ResurfaceResponse(BaseModel):
    notes: list[ResurfacedNoteResponse]
    total: int


class DigestEntryResponse(BaseModel):
    category: str
    title: str
    description: str
    fact_ids: list[str]
    timestamp: str


class DigestResponse(BaseModel):
    digest_type: str
    generated_at: str
    period_start: str
    period_end: str
    entries: list[DigestEntryResponse]
    summary: str


class DigestRequest(BaseModel):
    digest_type: str = "daily"
    since: str | None = None


class JobResultResponse(BaseModel):
    timestamp: str
    contradictions: int
    digest_summary: str
    entries: int


class SchedulerStatusResponse(BaseModel):
    running: bool
    jobs: list[dict]


# ── Routes ───────────────────────────────────────────────────────────

@router.post("/contradictions", response_model=ContradictionsResponse)
def detect_contradictions(req: ContradictionsRequest):
    """Detect contradictions in the knowledge graph."""
    from backend.surfacing.agent import SurfacingAgent

    pipeline = get_pipeline()
    agent = SurfacingAgent(graph=pipeline.graph, community=pipeline.community)
    flags = agent.detect_contradictions(since=req.since)

    return ContradictionsResponse(
        contradictions=[
            ContradictionFlagResponse(
                old_fact_id=f.old_fact_id,
                new_fact_id=f.new_fact_id,
                subject=f.subject,
                predicate=f.predicate,
                old_value=f.old_value,
                new_value=f.new_value,
                old_valid_from=f.old_valid_from,
                new_valid_from=f.new_valid_from,
                detected_at=f.detected_at,
                severity=f.severity,
            )
            for f in flags
        ],
        total=len(flags),
    )


@router.post("/resurface", response_model=ResurfaceResponse)
def resurface_notes(req: ResurfaceRequest):
    """Resurface stale-but-relevant notes."""
    from backend.surfacing.agent import SurfacingAgent

    pipeline = get_pipeline()
    agent = SurfacingAgent(graph=pipeline.graph, community=pipeline.community)
    notes = agent.resurface_relevant(
        context=req.context,
        top_k=req.top_k,
        max_age_days=req.max_age_days,
    )

    return ResurfaceResponse(
        notes=[
            ResurfacedNoteResponse(
                fact_id=n.fact_id,
                subject=n.subject,
                predicate=n.predicate,
                object_value=n.object_value,
                text=n.text,
                relevance_score=n.relevance_score,
                reason=n.reason,
                recorded_at=n.recorded_at,
            )
            for n in notes
        ],
        total=len(notes),
    )


@router.post("/digest", response_model=DigestResponse)
def generate_digest(req: DigestRequest):
    """Generate a digest report."""
    from backend.surfacing.agent import SurfacingAgent

    pipeline = get_pipeline()
    agent = SurfacingAgent(graph=pipeline.graph, community=pipeline.community)
    digest = agent.generate_digest(
        digest_type=req.digest_type,
        since=req.since,
    )

    return DigestResponse(
        digest_type=digest.digest_type,
        generated_at=digest.generated_at,
        period_start=digest.period_start,
        period_end=digest.period_end,
        entries=[
            DigestEntryResponse(
                category=e.category,
                title=e.title,
                description=e.description,
                fact_ids=e.fact_ids,
                timestamp=e.timestamp,
            )
            for e in digest.entries
        ],
        summary=digest.summary,
    )


@router.post("/run-daily", response_model=JobResultResponse)
def run_daily():
    """Trigger the daily surfacing job manually."""
    from backend.surfacing.scheduler import run_daily_now

    result = run_daily_now()
    return JobResultResponse(**result)


@router.post("/run-weekly", response_model=JobResultResponse)
def run_weekly():
    """Trigger the weekly surfacing job manually."""
    from backend.surfacing.scheduler import run_weekly_now

    result = run_weekly_now()
    return JobResultResponse(**result)


@router.get("/scheduler", response_model=SchedulerStatusResponse)
def scheduler_status():
    """Get scheduler status."""
    from backend.surfacing.scheduler import get_scheduler

    scheduler = get_scheduler()
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })

    return SchedulerStatusResponse(
        running=scheduler.running,
        jobs=jobs,
    )
