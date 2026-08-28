"""Ingestion API routes.

POST /ingest       — ingest a local file or directory
POST /ingest/url   — ingest a URL (browser clip / web page)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from backend.pipeline import Pipeline

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Shared pipeline instance (initialized lazily)
_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline


class IngestRequest(BaseModel):
    source: str  # file path or directory path
    source_type: str  # "markdown" or "pdf"


class IngestResponse(BaseModel):
    num_captures: int
    num_chunks: int
    doc_ids: list[str]


@router.post("", response_model=IngestResponse)
def ingest_local(req: IngestRequest):
    """Ingest a local file or directory."""
    path = Path(req.source)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Source not found: {req.source}")

    pipeline = get_pipeline()
    result = pipeline.ingest_source(req.source, req.source_type)
    return IngestResponse(**result)




@router.post("/file", response_model=IngestResponse)
async def ingest_uploaded_file(
    file: UploadFile = File(...),
    source_type: str = Form("markdown"),
):
    """Ingest an uploaded file (markdown or PDF)."""
    suffix = Path(file.filename or "file.md").suffix.lower()
    if suffix == ".pdf":
        source_type = "pdf"
    elif suffix == ".md":
        source_type = "markdown"

    # Write to a temp file, then ingest
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        pipeline = get_pipeline()
        result = pipeline.ingest_source(tmp_path, source_type)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return IngestResponse(**result)


class URLIngestRequest(BaseModel):
    url: str
    text: str | None = None  # Optional selected text (browser clip)
    title: str | None = None  # Optional page title


@router.post("/url", response_model=IngestResponse)
def ingest_url(req: URLIngestRequest):
    """Ingest a URL or browser clip (URL + selected text).

    Modes:
      - With text: browser clip mode — uses the provided text directly
      - Without text: fetch mode — fetches the URL and extracts readable content
    """
    pipeline = get_pipeline()

    if req.text:
        # Browser clip mode: use provided text directly
        from backend.ingestion.url_adapter import URLAdapter
        adapter = URLAdapter()
        capture = adapter.ingest_clip(
            url=req.url,
            selected_text=req.text,
            title=req.title or "",
        )
        result = pipeline.ingest_capture(capture)
        result["num_captures"] = 1
    else:
        # Fetch mode: fetch URL and extract content
        from backend.ingestion.url_adapter import URLAdapter
        adapter = URLAdapter()
        try:
            captures = adapter.ingest(req.url)
            result = {
                "num_captures": 0,
                "num_chunks": 0,
                "doc_ids": [],
            }
            for capture in captures:
                r = pipeline.ingest_capture(capture)
                result["num_captures"] += 1
                result["num_chunks"] += r["num_chunks"]
                result["doc_ids"].extend(r["doc_ids"])
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {e}")

    return IngestResponse(**result)


@router.get("/stats")
def get_stats():
    """Return storage stats."""
    pipeline = get_pipeline()
    return {
        "episodic_count": pipeline.store.count,
        "bm25_count": pipeline.bm25.count,
    }


@router.delete("/reset")
def reset_storage():
    """Reset all storage (for dev/testing)."""
    pipeline = get_pipeline()
    pipeline.store.reset()
    pipeline.bm25.clear()
    return {"status": "reset", "episodic_count": 0, "bm25_count": 0}
