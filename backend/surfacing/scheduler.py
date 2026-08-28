"""APScheduler integration for the surfacing agent.

Runs scheduled jobs:
  - Daily (8 AM): contradiction scan + daily digest
  - Weekly (Sunday 9 AM): full contradiction scan + weekly digest + community rebuild
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def start_scheduler(
    graph=None,
    community=None,
    daily_hour: int = 8,
    weekly_day: int = 0,  # Sunday
    weekly_hour: int = 9,
) -> BackgroundScheduler:
    """Start the surfacing agent scheduler.

    Args:
        graph: TemporalGraph instance (lazily loaded if None).
        community: CommunityStore instance (lazily loaded if None).
        daily_hour: Hour (UTC) for daily digest job.
        weekly_day: Day of week for weekly digest (0=Sunday).
        weekly_hour: Hour (UTC) for weekly digest job.
    """
    scheduler = get_scheduler()

    if scheduler.running:
        logger.warning("Scheduler already running")
        return scheduler

    # Daily contradiction scan + digest
    scheduler.add_job(
        _daily_job,
        CronTrigger(hour=daily_hour, minute=0),
        args=[graph, community],
        id="daily_digest",
        name="Daily contradiction scan + digest",
        replace_existing=True,
    )

    # Weekly full scan + community rebuild
    scheduler.add_job(
        _weekly_job,
        CronTrigger(day_of_week=weekly_day, hour=weekly_hour, minute=0),
        args=[graph, community],
        id="weekly_digest",
        name="Weekly full scan + community rebuild",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"Surfacing scheduler started: daily at {daily_hour}:00 UTC, "
        f"weekly on day {weekly_day} at {weekly_hour}:00 UTC"
    )
    return scheduler


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Surfacing scheduler stopped")
    _scheduler = None


def run_daily_now(graph=None, community=None) -> dict:
    """Run the daily job immediately (for testing/manual trigger)."""
    return _daily_job(graph, community)


def run_weekly_now(graph=None, community=None) -> dict:
    """Run the weekly job immediately (for testing/manual trigger)."""
    return _weekly_job(graph, community)


def _daily_job(graph=None, community=None) -> dict:
    """Daily job: contradiction scan + digest."""
    from backend.surfacing.agent import SurfacingAgent

    # Lazy-load graph from pipeline if not provided
    if graph is None:
        from backend.api.routes_ingest import get_pipeline
        pipeline = get_pipeline()
        graph = pipeline.graph
        community = pipeline.community

    agent = SurfacingAgent(graph=graph, community=community)

    # Detect contradictions
    contradictions = agent.detect_contradictions()
    logger.info(f"Daily scan: {len(contradictions)} contradictions found")

    # Generate daily digest
    digest = agent.generate_digest(digest_type="daily")
    logger.info(f"Daily digest: {digest.summary}")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contradictions": len(contradictions),
        "digest_summary": digest.summary,
        "entries": len(digest.entries),
    }


def _weekly_job(graph=None, community=None) -> dict:
    """Weekly job: full contradiction scan + community rebuild + digest."""
    from backend.surfacing.agent import SurfacingAgent

    if graph is None:
        from backend.api.routes_ingest import get_pipeline
        pipeline = get_pipeline()
        graph = pipeline.graph
        community = pipeline.community

    agent = SurfacingAgent(graph=graph, community=community)

    # Full contradiction scan
    contradictions = agent.detect_contradictions()
    logger.info(f"Weekly scan: {len(contradictions)} contradictions found")

    # Rebuild communities
    community_result = {}
    try:
        from backend.memory.community import cluster_facts, summarize_clusters
        clusters = cluster_facts(graph)
        if clusters:
            clusters = summarize_clusters(clusters, graph)
        community = community or __import__("backend.memory.community", fromlist=["CommunityStore"]).CommunityStore()
        for c in clusters:
            community.add_cluster(c)
        community_result = {"clusters_rebuilt": len(clusters)}
        logger.info(f"Weekly community rebuild: {len(clusters)} clusters")
    except Exception as e:
        logger.warning(f"Community rebuild failed: {e}")
        community_result = {"error": str(e)}

    # Generate weekly digest
    digest = agent.generate_digest(digest_type="weekly")
    logger.info(f"Weekly digest: {digest.summary}")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contradictions": len(contradictions),
        "community": community_result,
        "digest_summary": digest.summary,
        "entries": len(digest.entries),
    }
