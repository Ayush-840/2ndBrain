"""Graph query API routes.

POST /graph/query-as-of    — facts valid as of a date
POST /graph/entity         — entity neighborhood traversal
POST /graph/contradictions — find contradictions for a proposed fact
GET  /graph/stats          — graph statistics
GET  /graph/entities       — list all entities
POST /graph/extract        — on-demand extraction from text
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.routes_ingest import get_pipeline

router = APIRouter(prefix="/graph", tags=["graph"])


# ── Request / Response models ────────────────────────────────────────

class QueryAsOfRequest(BaseModel):
    date: str  # ISO8601 date
    entity: str | None = None
    predicate: str | None = None


class FactResponse(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    object: str
    object_literal: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    recorded_at: str
    confidence: float
    superseded_by: str | None = None
    source_episode_id: str = ""


class QueryAsOfResponse(BaseModel):
    facts: list[FactResponse]
    total: int
    date: str


class EntityNeighborsRequest(BaseModel):
    entity_id: str
    hops: int = 1
    valid_as_of: str | None = None


class EntityNeighborsResponse(BaseModel):
    entity_id: str
    neighbors: list[FactResponse]
    total: int


class ContradictionRequest(BaseModel):
    subject: str
    predicate: str
    object_value: str
    valid_from: str | None = None
    valid_to: str | None = None


class ContradictionResponse(BaseModel):
    contradictions: list[FactResponse]
    total: int


class GraphStatsResponse(BaseModel):
    entities: int
    facts: int
    active_facts: int
    total_nodes: int


class ExtractRequest(BaseModel):
    text: str
    source_context: str = ""


class ExtractResponse(BaseModel):
    entities_added: int
    facts_added: int
    contradictions_found: int
    graph_stats: GraphStatsResponse


class EntityListItem(BaseModel):
    entity_id: str
    label: str
    entity_type: str


class EntityListResponse(BaseModel):
    entities: list[EntityListItem]
    total: int


# ── Helper ───────────────────────────────────────────────────────────

def _fact_to_response(fact: dict) -> FactResponse:
    return FactResponse(
        fact_id=fact.get("fact_id", ""),
        subject=fact.get("subject", ""),
        predicate=fact.get("predicate", ""),
        object=fact.get("object", ""),
        object_literal=fact.get("object_literal"),
        valid_from=fact.get("valid_from"),
        valid_to=fact.get("valid_to"),
        recorded_at=fact.get("recorded_at", ""),
        confidence=fact.get("confidence", 1.0),
        superseded_by=fact.get("superseded_by"),
        source_episode_id=fact.get("source_episode_id", ""),
    )


# ── Routes ───────────────────────────────────────────────────────────

@router.post("/query-as-of", response_model=QueryAsOfResponse)
def query_as_of(req: QueryAsOfRequest):
    """Return facts that were valid as of a specific date."""
    pipeline = get_pipeline()
    try:
        facts = pipeline.graph.query_as_of(
            req.date, entity=req.entity, predicate=req.predicate
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return QueryAsOfResponse(
        facts=[_fact_to_response(f) for f in facts],
        total=len(facts),
        date=req.date,
    )


@router.post("/entity", response_model=EntityNeighborsResponse)
def get_entity_neighbors(req: EntityNeighborsRequest):
    """Return facts within N hops of an entity."""
    pipeline = get_pipeline()
    if not pipeline.graph.has_entity(req.entity_id):
        raise HTTPException(status_code=404, detail=f"Entity not found: {req.entity_id}")

    facts = pipeline.graph.neighbors(
        req.entity_id,
        hops=req.hops,
        valid_as_of=req.valid_as_of,
    )

    return EntityNeighborsResponse(
        entity_id=req.entity_id,
        neighbors=[_fact_to_response(f) for f in facts],
        total=len(facts),
    )


@router.post("/contradictions", response_model=ContradictionResponse)
def find_contradictions(req: ContradictionRequest):
    """Find existing facts that contradict a proposed new fact."""
    pipeline = get_pipeline()
    contradictions = pipeline.graph.find_contradictions(
        subject_id=req.subject,
        predicate=req.predicate,
        object_value=req.object_value,
        valid_from=req.valid_from,
        valid_to=req.valid_to,
    )

    return ContradictionResponse(
        contradictions=[_fact_to_response(f) for f in contradictions],
        total=len(contradictions),
    )


@router.get("/stats", response_model=GraphStatsResponse)
def graph_stats():
    """Return graph statistics."""
    pipeline = get_pipeline()
    stats = pipeline.graph.stats()
    return GraphStatsResponse(**stats)


@router.get("/entities", response_model=EntityListResponse)
def list_entities(entity_type: str | None = None):
    """List all entities, optionally filtered by type."""
    pipeline = get_pipeline()
    entities = pipeline.graph.list_entities(entity_type=entity_type)
    return EntityListResponse(
        entities=[
            EntityListItem(
                entity_id=e["entity_id"],
                label=e["label"],
                entity_type=e["entity_type"],
            )
            for e in entities
        ],
        total=len(entities),
    )


@router.post("/extract", response_model=ExtractResponse)
def extract_on_demand(req: ExtractRequest):
    """Run LLM extraction on arbitrary text and store results in the graph."""
    pipeline = get_pipeline()
    result = pipeline.extract_and_store(req.text, source_context=req.source_context)
    return ExtractResponse(
        entities_added=result["entities_added"],
        facts_added=result["facts_added"],
        contradictions_found=result["contradictions_found"],
        graph_stats=GraphStatsResponse(**result["graph_stats"]),
    )


# ── Graph export for Cytoscape.js ──────────────────────────────────

# Style hints: map entity types to visual properties
ENTITY_TYPE_COLORS = {
    "person": "#4A90D9",
    "concept": "#7B68EE",
    "technique": "#2ECC71",
    "tool": "#E67E22",
    "paper": "#E74C3C",
    "organization": "#1ABC9C",
    "literal": "#95A5A6",
}

# Map common predicates to edge colors
PREDICATE_COLORS = {
    "believes": "#9B59B6",
    "works_on": "#3498DB",
    "uses": "#2ECC71",
    "implements": "#27AE60",
    "depends_on": "#E74C3C",
    "supersedes": "#E67E22",
    "will_migrate_to": "#F39C12",
    "built_with": "#1ABC9C",
}


class GraphExportResponse(BaseModel):
    elements: list[dict]
    node_count: int
    edge_count: int
    entity_types: list[str]
    predicates: list[str]


@router.get("/export", response_model=GraphExportResponse)
def export_graph(
    valid_as_of: str | None = None,
    entity_type: str | None = None,
    include_superseded: bool = False,
):
    """Export the knowledge graph in Cytoscape.js format.

    Returns a flat array of node/edge elements ready for Cytoscape.js:
    [
      { "group": "nodes", "data": { "id": "...", "label": "...", ... } },
      { "group": "edges", "data": { "id": "...", "source": "...", "target": "...", ... } }
    ]

    Query params:
      valid_as_of: filter edges to those valid at this date
      entity_type: filter nodes to this entity type
      include_superseded: include superseded edges (default: false)
    """
    pipeline = get_pipeline()
    graph = pipeline.graph

    elements: list[dict] = []
    seen_nodes: set[str] = set()
    entity_types_used: set[str] = set()
    predicates_used: set[str] = set()

    # Get all facts (optionally filtered)
    if valid_as_of:
        facts = graph.query_as_of(valid_as_of)
    else:
        facts = graph.query_all_facts(include_superseded=include_superseded)

    for fact in facts:
        subject_id = fact["subject"]
        object_id = fact["object"]
        predicate = fact.get("predicate", "")
        fact_id = fact.get("fact_id", "")

        # Add subject node if not seen
        add_subject = True
        if subject_id not in seen_nodes and not subject_id.startswith("_literal:"):
            entity = graph.get_entity(subject_id)
            if entity:
                etype = entity.get("entity_type", "concept")
                if entity_type and etype != entity_type:
                    add_subject = False
                else:
                    entity_types_used.add(etype)
                    elements.append({
                        "group": "nodes",
                        "data": {
                            "id": subject_id,
                            "label": entity.get("label", subject_id),
                            "entity_type": etype,
                            "color": ENTITY_TYPE_COLORS.get(etype, "#95A5A6"),
                        },
                    })
                    seen_nodes.add(subject_id)

        # Add object node if not seen
        add_object = True
        if object_id not in seen_nodes:
            if object_id.startswith("_literal:"):
                # Literal node
                lit_label = object_id[len("_literal:")]
                elements.append({
                    "group": "nodes",
                    "data": {
                        "id": object_id,
                        "label": lit_label[:50],  # truncate long literals
                        "entity_type": "literal",
                        "color": ENTITY_TYPE_COLORS["literal"],
                    },
                })
                seen_nodes.add(object_id)
            else:
                entity = graph.get_entity(object_id)
                if entity:
                    etype = entity.get("entity_type", "concept")
                    if entity_type and etype != entity_type:
                        add_object = False
                    else:
                        entity_types_used.add(etype)
                    elements.append({
                        "group": "nodes",
                        "data": {
                            "id": object_id,
                            "label": entity.get("label", object_id),
                            "entity_type": etype,
                            "color": ENTITY_TYPE_COLORS.get(etype, "#95A5A6"),
                        },
                    })
                    seen_nodes.add(object_id)

        # Add edge
        predicates_used.add(predicate)
        vf = fact.get("valid_from")
        vt = fact.get("valid_to")
        temporal_label = ""
        if vf:
            temporal_label = vf
            if vt:
                temporal_label += f" → {vt}"
            else:
                temporal_label += " → present"

        elements.append({
            "group": "edges",
            "data": {
                "id": fact_id,
                "source": subject_id,
                "target": object_id,
                "predicate": predicate,
                "label": predicate.replace("_", " "),
                "color": PREDICATE_COLORS.get(predicate, "#BDC3C7"),
                "valid_from": vf,
                "valid_to": vt,
                "temporal": temporal_label,
                "confidence": fact.get("confidence", 1.0),
                "superseded": bool(fact.get("superseded_by")),
            },
        })

    return GraphExportResponse(
        elements=elements,
        node_count=len(seen_nodes),
        edge_count=len(elements) - len(seen_nodes),
        entity_types=sorted(entity_types_used),
        predicates=sorted(predicates_used),
    )
