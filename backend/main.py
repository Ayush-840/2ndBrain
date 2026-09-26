"""Second-Brain: FastAPI application.

Run with:
    uvicorn backend.main:app --reload

Run with NiceGUI frontend:
    python -m backend.main
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_community import router as community_router
from backend.api.routes_documents import router as documents_router
from backend.api.routes_graph import router as graph_router
from backend.api.routes_ingest import get_pipeline
from backend.api.routes_ingest import router as ingest_router
from backend.api.routes_ingest_whatsapp import router as whatsapp_router
from backend.api.routes_profile import router as profile_router
from backend.api.routes_query import router as query_router
from backend.api.routes_surfacing import router as surfacing_router
from backend.security import validate_security


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate security posture, then initialize the pipeline."""
    validate_security()
    pipeline = get_pipeline()
    # Auto-build communities if clusters are empty (rebuilt from the graph)
    if pipeline.community.total_facts_in_clusters == 0:
        try:
            pipeline.build_communities(max_clusters=10, summarize=False)
        except Exception:
            pass  # OK if no data yet
    yield
    # Durable knowledge graph: persist on graceful shutdown (atexit covers
    # hard exits, and mutating requests save as they go).
    try:
        pipeline.save_state()
    except Exception:
        logger.warning("graph not saved on shutdown", exc_info=True)


logger = logging.getLogger(__name__)

app = FastAPI(
    title="2ndBrain",
    description="Personal second brain with bi-temporal memory graph",
    version="0.1.0",
    redirect_slashes=False,
    lifespan=lifespan,
)

# CORS for local dev (Vite frontend on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def persist_graph_after_mutations(request, call_next):
    """Save the knowledge graph after any successful mutating request.

    Only saves a pipeline that already exists — never constructs one — so
    tests and read-only traffic are unaffected.
    """
    response = await call_next(request)
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 500:
        from backend.api import routes_ingest as _ingest

        if _ingest._pipeline is not None:
            _ingest._pipeline.save_state()
    return response


app.include_router(ingest_router)
app.include_router(whatsapp_router)
app.include_router(documents_router)
app.include_router(query_router)
app.include_router(graph_router)
app.include_router(community_router)
app.include_router(surfacing_router)
app.include_router(profile_router)


@app.get("/")
def root():
    return {
        "name": "2ndBrain",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "frontend": "/ui",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# ── NiceGUI frontend (mounts at /ui) ───────────────────────────────
try:
    from backend.frontend.app import create_frontend
    create_frontend(app)
except ImportError:
    pass  # nicegui not installed — API-only mode


def main():
    """Run with NiceGUI (recommended for full experience)."""
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()

