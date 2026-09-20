"""Focal area bounding box and projection — extracted from routes/search.py."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.core.config import settings


def extract_positions(nodes: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Pull (x, y) from each node. Supports x/y, position:{x,y}, layout:{x,y}."""
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


def compute_focal_area(nodes: List[Dict[str, Any]]) -> Dict[str, float]:
    """Bounding-box focal area. Returns {cx, cy, zoom}."""
    pts = extract_positions(nodes)
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

    if extent < 1e-6:
        return {"cx": cx, "cy": cy, "zoom": 1.2}

    base_zoom = 2.0
    zoom = base_zoom / extent * settings.FOCAL_PADDING
    zoom = max(0.05, min(8.0, zoom))
    return {"cx": cx, "cy": cy, "zoom": zoom}


def project_to_search_shape(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Slim heavy search nodes down to what the FE needs."""
    slim_nodes = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("nodeId") or n.get("id") or n.get("elementId")
        if not nid:
            continue
        name = n.get("nodeName") or n.get("label") or n.get("name") or nid
        slim_nodes.append({
            "nodeId": nid,
            "nodeName": name,
            "similarityScore": n.get("similarity_score"),
        })
    return {"nodes": slim_nodes, "edges": []}
