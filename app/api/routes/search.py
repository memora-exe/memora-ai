"""Phase 3 — AI Graph Search.

POST /api/search
Body: { q, project_id, jwt_token }
Returns: { nodes, edges, focalArea: { cx, cy, zoom } }

Reuses llm_hybrid_search from graph_tools.
"""
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.graph_tools import llm_hybrid_search

router = APIRouter(prefix="/api", tags=["AI Search"])


class SearchRequest(BaseModel):
    q: str
    project_id: str
    jwt_token: str


def _extract_positions(nodes: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Pull (x, y) from each node. Supports keys: x/y, position:{x,y}, layout:{x,y}.
    Falls back to (0,0) when no position info is present."""
    pts: List[Tuple[float, float]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if "x" in n and "y" in n:
            try:
                pts.append((float(n["x"]), float(n["y"])))
                continue
            except (TypeError, ValueError):
                pass
        pos = n.get("position") or n.get("layout")
        if isinstance(pos, dict):
            try:
                pts.append((float(pos["x"]), float(pos["y"])))
                continue
            except (KeyError, TypeError, ValueError):
                pass
        pts.append((0.0, 0.0))
    return pts


def _compute_focal_area(nodes: List[Dict[str, Any]]) -> Dict[str, float]:
    """Bounding-box focal area. Returns {cx, cy, zoom}.
    If positions are missing (all 0,0), synthesizes a centered circle of radius 100."""
    pts = _extract_positions(nodes)
    if not pts:
        return {"cx": 0.0, "cy": 0.0, "zoom": 1.0}

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max_x - min_x
    h = max_y - min_y
    cx = min_x + w / 2
    cy = min_y + h / 2
    extent = max(w, h)

    # If all positions collapsed (no real layout data), center at origin with zoom 1.2
    if extent < 1e-6:
        return {"cx": cx, "cy": cy, "zoom": 1.2}

    base_zoom = 2.0
    zoom = base_zoom / extent * settings.FOCAL_PADDING
    # clamp to renderer zoom bounds 0.05..8
    zoom = max(0.05, min(8.0, zoom))
    return {"cx": cx, "cy": cy, "zoom": zoom}


def _project_to_search_shape(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Slim the heavy llm_hybrid_search nodes/edges down to what the FE needs."""
    slim_nodes = [
        {
            "nodeId": n.get("id"),
            "nodeName": n.get("label") or n.get("name") or n.get("id"),
            "nodeType": n.get("type") or n.get("nodeType"),
            "similarityScore": n.get("similarity_score"),
        }
        for n in nodes
        if isinstance(n, dict) and n.get("id")
    ]
    return {"nodes": slim_nodes, "edges": []}


@router.post("/search")
async def ai_search(request: SearchRequest):
    if not request.q or not request.q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")

    result = llm_hybrid_search(
        project_id=request.project_id,
        query=request.q,
        jwt_token=request.jwt_token,
        k=settings.SEARCH_TOP_K,
    )

    if "error" in result and not result.get("nodes"):
        raise HTTPException(status_code=502, detail=result["error"])

    nodes = result.get("nodes") or []
    slim = _project_to_search_shape(nodes)
    focal_area = _compute_focal_area(nodes)

    return {**slim, "focalArea": focal_area}