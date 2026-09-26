"""Personal-memory API — profile, timeline, goals, reminders, review queue.

Implements the Personal Memory Module surface from the research paper §2.1
and the additions in 06-additional-features §1, mapped onto the existing
temporal graph instead of the Postgres schema sketched in 08-trd §3:

GET  /profile                          — current fields (sensitive ones decrypted)
POST /profile                          — set a field (close-old / insert-new)
GET  /profile/history?field=           — bi-temporal history of one field
GET  /profile/relationships            — family/contacts as graph edges
POST /profile/people                   — add a person + relation edge
GET  /profile/goals                    — goals with check-in history
POST /profile/goals                    — create a goal
POST /profile/goals/{id}/checkins      — append a progress check-in
GET  /profile/timeline                 — life timeline (chronological)
POST /profile/timeline                 — add a timeline event
GET  /reminders?window_days=30         — unified reminder feed (docs + goals + events)
GET  /contradictions?status=PENDING    — review queue (TRD §3 contradiction_flags)
POST /contradictions/{id}/resolve      — accept / reject a proposed value
GET  /audit-log?limit=100              — append-only access log (extensions §4)
GET  /export                           — full data export, zipped (extensions §4)
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from backend.api.routes_ingest import get_pipeline
from backend.config import settings
from backend.memory import audit
from backend.memory.blob_store import BlobStore
from backend.memory.profile import USER_ID, ProfileStore
from backend.memory.review_queue import PENDING, ReviewQueue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profile"])


# ── Request models ───────────────────────────────────────────────────


class ProfileFieldRequest(BaseModel):
    field: str = Field(min_length=2, max_length=60)
    value: str = Field(min_length=1, max_length=2000)


class PersonRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relation: str = Field(min_length=1, max_length=60)
    notes: str = ""
    contact: str = ""


class GoalRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = "General"
    description: str = ""
    target_date: str | None = None


class CheckInRequest(BaseModel):
    percent: int = Field(ge=0, le=100)
    note: str = ""


class EventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    event_date: str | None = None
    category: str = "General"
    description: str = ""
    document_id: str | None = None


class ResolveRequest(BaseModel):
    accept: bool
    value: str | None = None  # optional override for the accepted value


# ── Helpers ──────────────────────────────────────────────────────────


def _profile() -> ProfileStore:
    return ProfileStore(get_pipeline().graph)


def _queue() -> ReviewQueue:
    return ReviewQueue()


def _days_until(value: str, now: datetime) -> int | None:
    """Days from now; accepts date-only (naive) or full ISO datetimes."""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (dt - now).days


# ── Profile ──────────────────────────────────────────────────────────


@router.get("/profile")
def get_profile() -> dict:
    """Current structured facts (G1: instant, no LLM roundtrip)."""
    store = _profile()
    fields = store.get_profile()
    return {
        "fields": fields,
        "counts": store.counts(),
        "encrypted_fields": sorted(f for f in fields if f in settings.sensitive_fields),
        "user_id": USER_ID,
    }


@router.post("/profile")
def set_profile_field(req: ProfileFieldRequest) -> dict:
    """Set one field — supersedes the old value instead of overwriting."""
    try:
        result = _profile().set_field(req.field, req.value, source="api")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record(
        "edit_profile",
        target_id=result.get("new_fact_id"),
        detail=f"{result['field']} updated",
    )
    return result


@router.get("/profile/history")
def profile_history(field: str) -> dict:
    """What this field said before — every value, with validity windows."""
    rows = _profile().history(field)
    return {"field": field, "history": rows, "total": len(rows)}


# ── Family / contacts graph (extensions §1) ──────────────────────────


@router.get("/profile/relationships")
def relationships() -> dict:
    rows = _profile().relationships()
    return {"relationships": rows, "total": len(rows)}


@router.post("/profile/people")
def add_person(req: PersonRequest) -> dict:
    try:
        pid = _profile().add_person(
            req.name, req.relation, notes=req.notes, contact=req.contact
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record("edit_profile", target_id=pid, detail=f"person {req.name} added")
    return {"person_id": pid, "name": req.name, "relation": req.relation}


# ── Goals + check-ins (extensions §1) ────────────────────────────────


@router.get("/profile/goals")
def goals() -> dict:
    rows = _profile().list_goals()
    return {"goals": rows, "total": len(rows)}


@router.post("/profile/goals")
def create_goal(req: GoalRequest) -> dict:
    try:
        gid = _profile().add_goal(
            req.title,
            category=req.category,
            description=req.description,
            target_date=req.target_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record("edit_profile", target_id=gid, detail=f"goal {req.title}")
    return {"goal_id": gid, "title": req.title}


@router.post("/profile/goals/{goal_id}/checkins")
def goal_check_in(goal_id: str, req: CheckInRequest) -> dict:
    try:
        return _profile().goal_check_in(goal_id, req.percent, req.note)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 422,
                            detail=str(exc)) from exc


# ── Life timeline (extensions §1) ────────────────────────────────────


@router.get("/profile/timeline")
def timeline() -> dict:
    rows = _profile().list_events()
    return {"events": rows, "total": len(rows)}


@router.post("/profile/timeline")
def add_timeline_event(req: EventRequest) -> dict:
    try:
        eid = _profile().add_event(
            req.title,
            event_date=req.event_date,
            category=req.category,
            description=req.description,
            document_id=req.document_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record("edit_profile", target_id=eid, detail=f"event {req.title}")
    return {"event_id": eid, "title": req.title}


# ── Unified reminder feed (extensions §1 / PRD G4) ───────────────────


@router.get("/reminders")
def reminders(window_days: int | None = None) -> dict:
    """Document expiries + goal deadlines + upcoming timeline events."""
    horizon = window_days or settings.reminder_window_days
    graph = get_pipeline().graph
    now = datetime.now(UTC)
    items: list[dict] = []

    for doc in graph.documents_expiring(within_days=horizon):
        items.append(
            {
                "kind": "document",
                "id": doc.get("document_id"),
                "title": doc.get("title") or doc.get("filename") or "document",
                "remind_on": doc.get("valid_until"),
                "days_left": doc.get("days_left"),
                "urgency": doc.get("status"),
                "detail": doc.get("usage_context"),
            }
        )

    store = _profile()
    for goal in store.list_goals():
        target = goal.get("target_date")
        if not target or goal.get("status") in ("done", "completed"):
            continue
        days_left = _days_until(target, now)
        if days_left is None or days_left > horizon:
            continue
        items.append(
            {
                "kind": "goal",
                "id": goal["goal_id"],
                "title": goal["title"],
                "remind_on": target,
                "days_left": days_left,
                "urgency": "red" if days_left <= 0 else ("amber" if days_left <= max(1, horizon // 3) else "green"),
                "detail": goal.get("category"),
            }
        )

    for event in store.list_events():
        date = event.get("event_date")
        if not date:
            continue
        days_left = _days_until(date, now)
        if days_left is None or not -1 <= days_left <= horizon:
            items.append(
                {
                    "kind": "event",
                    "id": event["event_id"],
                    "title": event["title"],
                    "remind_on": date,
                    "days_left": days_left,
                    "urgency": "amber" if days_left >= 0 else "green",
                    "detail": event.get("category"),
                }
            )

    items.sort(key=lambda i: (i["days_left"] is None, i["days_left"]))
    return {"window_days": horizon, "reminders": items, "total": len(items)}


# ── Contradiction review queue (TRD §3 / PRD G3) ─────────────────────


@router.get("/contradictions")
def list_contradictions(status: str = PENDING) -> dict:
    """Review queue — syncs from the graph first so new conflicts show up."""
    queue = _queue()
    try:
        queue.sync(get_pipeline().graph)
    except Exception:
        logger.warning("contradiction sync failed", exc_info=True)
    items = queue.list(status=status)
    return {
        "contradictions": items,
        "total": len(items),
        "stats": queue.stats(),
    }


@router.post("/contradictions/{item_id}/resolve")
def resolve_contradiction(item_id: str, req: ResolveRequest) -> dict:
    """Explicit accept/reject — never a silent profile mutation (PRD §10)."""
    queue = _queue()
    try:
        item = queue.resolve(
            item_id, accept=req.accept, value=req.value, graph=get_pipeline().graph
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit.record(
        "resolve_contradiction",
        target_id=item_id,
        detail=f"{'accepted' if req.accept else 'rejected'} {item.get('predicate')}",
    )
    return item


# ── Audit log (extensions §4) ────────────────────────────────────────


@router.get("/audit-log")
def audit_log(limit: int = 100, action: str | None = None) -> dict:
    entries = audit.read(limit=limit, action=action)
    return {"entries": entries, "total": len(entries), "logged": audit.count()}


# ── Full data export (extensions §4 / TRD §7 portability) ────────────


@router.get("/export")
def export_data() -> Response:
    """Everything, zipped: graph, profile, queue, audit log, original files."""
    import tempfile

    graph = get_pipeline().graph
    store = _profile()
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            graph.save(tmp.name)
            zf.writestr("graph.json", Path(tmp.name).read_text(encoding="utf-8"))
            Path(tmp.name).unlink(missing_ok=True)
        zf.writestr(
            "profile.json",
            json.dumps(store.get_profile(), indent=2, ensure_ascii=False),
        )
        zf.writestr(
            "timeline.json",
            json.dumps(store.list_events(), indent=2, ensure_ascii=False),
        )
        zf.writestr(
            "goals.json",
            json.dumps(store.list_goals(), indent=2, ensure_ascii=False),
        )
        zf.writestr(
            "relationships.json",
            json.dumps(store.relationships(), indent=2, ensure_ascii=False),
        )
        zf.writestr(
            "contradictions.json",
            json.dumps(_queue().list(status="ALL"), indent=2, ensure_ascii=False),
        )
        if Path(settings.audit_log_path).exists():
            zf.write(settings.audit_log_path, arcname="audit.log.jsonl")

        # Original document bytes (decrypted on read by the blob store)
        try:
            blob = BlobStore()
            for doc in graph.list_documents():
                blob_path = doc.get("blob_path")
                if not blob_path or not blob.exists(blob_path):
                    continue
                safe = (doc.get("filename") or doc.get("document_id", "doc")).replace("/", "_")
                zf.writestr(f"documents/{safe}", blob.get(blob_path))
        except Exception:
            logger.warning("document blobs not included in export", exc_info=True)

        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "exported_at": datetime.now(UTC).isoformat(),
                    "documents": graph.document_count,
                    "entities": graph.entity_count,
                    "facts": graph.fact_count,
                    "profile_fields": len(store.get_profile()),
                },
                indent=2,
            ),
        )

    audit.record("export", detail="full data export")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="2ndbrain-export.zip"'},
    )
