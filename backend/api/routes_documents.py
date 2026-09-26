"""Document API routes — Phase 7 surface for the Document node.

GET  /documents                 — browse purpose-tagged documents
GET  /documents/expiring        — what needs attention soon (feeds digest + WhatsApp nudges)
GET  /documents/status          — capture-source health for the Inbox status strip
GET  /documents/{id}            — one document
GET  /documents/{id}/file       — original bytes, decrypted on read
POST /documents/{id}/correct    — supersede the purpose (UI edit + WhatsApp reply share this)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from backend.api.routes_ingest import get_pipeline
from backend.config import settings
from backend.enrichment.purpose import parse_expiry_date, tag_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_status(doc: dict) -> str:
    """🟢 / 🟡 / 🔴 chip for the UI: is this document about to go stale?"""
    until = doc.get("valid_until")
    if not until:
        return "none"
    try:
        dt = datetime.fromisoformat(str(until))
    except ValueError:
        return "none"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    days_left = (dt - datetime.now(UTC)).days
    window = settings.document_expiry_warning_days
    if days_left > window:
        return "green"
    if days_left > max(1, window // 3):
        return "amber"
    return "red"


def _serialize(doc: dict) -> dict:
    out = dict(doc)
    out["status"] = _doc_status(doc)
    if doc.get("valid_until"):
        try:
            out["days_left"] = (
                datetime.fromisoformat(str(doc["valid_until"])).replace(tzinfo=UTC)
                - datetime.now(UTC)
            ).days
        except ValueError:
            out["days_left"] = None
    else:
        out["days_left"] = None
    out["has_file"] = bool(doc.get("blob_path"))
    return out


# ── Specific routes first (FastAPI matches in registration order) ────


@router.get("/expiring")
def documents_expiring(days: int | None = None):
    """Documents whose valid_until is within N days (default from config)."""
    pipeline = get_pipeline()
    window = days or settings.document_expiry_warning_days
    docs = pipeline.graph.documents_expiring(window)
    return {"total": len(docs), "window_days": window, "documents": [_serialize(d) for d in docs]}


@router.get("/status")
def capture_status():
    """Health of each capture source — powers the Inbox status strip."""
    pipeline = get_pipeline()
    docs = pipeline.graph.list_documents()

    last_whatsapp = None
    last_vault = None
    for doc in docs:
        channel = doc.get("source_channel")
        recorded = doc.get("recorded_at")
        if channel == "whatsapp" and last_whatsapp is None:
            last_whatsapp = recorded
        elif channel in ("markdown", "vault") and last_vault is None:
            last_vault = recorded

    vault_dir = settings.vault_dir
    return {
        "whatsapp": {
            "configured": settings.whatsapp_enabled,
            "ready": settings.whatsapp_ready,
            "last_capture": last_whatsapp,
        },
        "vault": {
            "dir": str(vault_dir),
            "exists": vault_dir.exists() if hasattr(vault_dir, "exists") else False,
            "last_capture": last_vault,
        },
    }


class CorrectionRequest(BaseModel):
    usage_context: str = Field(min_length=1, max_length=1000)
    purpose_tags: list[str] | None = None
    valid_until: str | None = None


@router.post("/{doc_id}/correct")
def correct_document(doc_id: str, req: CorrectionRequest):
    """Supersede a document's purpose — never overwrite the old version."""
    pipeline = get_pipeline()
    old = pipeline.graph.get_document(doc_id)
    if old is None:
        raise HTTPException(status_code=404, detail=f"No document: {doc_id}")

    tags = [t.lower().strip() for t in (req.purpose_tags if req.purpose_tags is not None else tag_text(req.usage_context))]
    if not tags:
        tags = old.get("purpose_tags", [])
    if tags == ["other"] and old.get("purpose_tags"):
        tags = old["purpose_tags"]

    valid_until = req.valid_until or parse_expiry_date(req.usage_context) or old.get("valid_until")

    new_doc = pipeline.graph.correct_document(
        doc_id,
        usage_context=req.usage_context.strip(),
        purpose_tags=tags,
        valid_until=valid_until,
    )
    if new_doc is None:
        raise HTTPException(status_code=409, detail="Document already superseded")

    from backend.memory import audit

    audit.record(
        "edit_document", target_id=doc_id, detail=f"purpose → {req.usage_context[:80]}"
    )
    return {"superseded": doc_id, "document": _serialize(new_doc)}


@router.get("")
def list_documents(tag: str | None = None, include_superseded: bool = False):
    """List documents, newest first, optionally filtered by purpose tag."""
    pipeline = get_pipeline()
    docs = pipeline.graph.list_documents(
        purpose_tag=tag,
        include_superseded=include_superseded,
    )
    tags: list[str] = []
    for doc in pipeline.graph.list_documents():
        for t in doc.get("purpose_tags", []):
            if t not in tags:
                tags.append(t)
    return {
        "total": len(docs),
        "tags": sorted(tags),
        "documents": [_serialize(d) for d in docs],
    }


@router.get("/{doc_id}")
def get_document(doc_id: str):
    pipeline = get_pipeline()
    doc = pipeline.graph.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No document: {doc_id}")
    return _serialize(doc)


@router.get("/{doc_id}/file")
def download_document(doc_id: str):
    """Serve the original file, decrypted on read (never stored in plaintext)."""
    pipeline = get_pipeline()
    doc = pipeline.graph.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No document: {doc_id}")
    blob_path = doc.get("blob_path")
    if not blob_path:
        raise HTTPException(status_code=404, detail="No stored file for this document")

    from backend.memory import audit
    from backend.memory.blob_store import BlobStore

    audit.record("view_document", target_id=doc_id, detail=doc.get("filename"))

    try:
        data = BlobStore().get(blob_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = doc.get("filename") or f"{doc_id}.bin"
    return Response(
        content=data,
        media_type=doc.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
