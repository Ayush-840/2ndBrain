"""Second-Brain: FastAPI application.

Run with:
    uvicorn backend.main:app --reload

Run with NiceGUI frontend:
    python -m backend.main
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_ingest import router as ingest_router, get_pipeline
from backend.api.routes_query import router as query_router
from backend.api.routes_graph import router as graph_router
from backend.api.routes_community import router as community_router
from backend.api.routes_surfacing import router as surfacing_router

app = FastAPI(
    title="2ndBrain",
    description="Personal second brain with bi-temporal memory graph",
    version="0.1.0",
    redirect_slashes=False,
)

# CORS for local dev (Vite frontend on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(graph_router)
app.include_router(community_router)
app.include_router(surfacing_router)


@app.on_event("startup")
def startup_event():
    get_pipeline()


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

