"""Phase 4 — Knowledge Insights Dashboard (Capability 3).

Computes structural graph analytics:
  - node/edge counts from the existing NestJS graph endpoints
  - top high-degree hubs (computed in Python)
  - topicCoverage by nodeTypeId
  - low-degree gaps (degree < INSIGHTS_DEGREE_GAP_THRESHOLD)
  - connected components via Python BFS
  - LLM-synthesized recommendations (markdown)

YAGNI: no caching, no async pipeline, no separate Neo4j client. Uses the
NestJS proxy that graph_tools already speaks; everything else is a single
pass over the fetched graph.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.common.logger.logger import get_logger
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.services.graph_tools import get_project_edges, get_project_nodes
from app.services.llm import get_chat_model

logger = get_logger("InsightsEngine")

DEFAULT_HUB_LIMIT = 5
DEFAULT_GAP_LIMIT = 20


async def compute_insights(project_id: str, jwt_token: str | None = None) -> Dict[str, Any]:
    """Return the dashboard payload (stats + recommendations).

    `jwt_token` is forwarded only when the NestJS endpoints require it;
    when omitted, the dashboard stats become empty but the call still
    succeeds (useful for unauthenticated health probes).
    """
    nodes_resp = _safe(get_project_nodes, project_id, jwt_token) if jwt_token else []
    edges_resp = _safe(get_project_edges, project_id, jwt_token) if jwt_token else []

    nodes = _as_list(nodes_resp)
    edges = _as_list(edges_resp)

    # ── Counts ─────────────────────────────────────────────────────────────
    node_count = len(nodes)
    edge_count = len(edges)

    # ── Degree + Topic + Gaps computed in Python over fetched nodes/edges ─
    degree_map = _degree_map(edges)
    important_nodes = _top_hubs(nodes, degree_map, DEFAULT_HUB_LIMIT)
    topic_coverage = _topic_coverage(nodes)
    gaps = _gaps(nodes, degree_map, settings.INSIGHTS_DEGREE_GAP_THRESHOLD, DEFAULT_GAP_LIMIT)

    # ── Connected components ───────────────────────────────────────────────
    components, fragmentation = _bfs_components(nodes, edges)

    # ── LLM recommendations ───────────────────────────────────────────────
    recommendations = await _synthesize_recommendations(
        node_count=node_count,
        edge_count=edge_count,
        important_nodes=important_nodes,
        topic_coverage=topic_coverage,
        gaps=gaps,
        fragmentation=fragmentation,
    )

    return {
        "stats": {"nodes": node_count, "edges": edge_count},
        "importantNodes": important_nodes,
        "topicCoverage": topic_coverage,
        "gaps": gaps,
        "weakLinks": [],
        "fragmentation": fragmentation,
        "components": components,
        "recommendations": recommendations,
    }


# ── helpers ────────────────────────────────────────────────────────────────


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        logger.warning(f"{fn.__name__} failed: {e}")
        return None


def _as_list(resp: Any) -> list:
    """Coerce graph_tools return (list / dict / wrapped) into a flat list."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        if "error" in resp:
            return []
        for key in ("data", "nodes", "edges", "items", "results"):
            if key in resp and isinstance(resp[key], list):
                return resp[key]
    return []


def _node_id(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    return node.get("id") or node.get("nodeId") or node.get("uuid")


def _edge_endpoints(edge: Any) -> tuple[str | None, str | None]:
    if not isinstance(edge, dict):
        return (None, None)
    src = edge.get("sourceNodeId") or edge.get("source") or edge.get("from")
    dst = edge.get("targetNodeId") or edge.get("target") or edge.get("to")
    return (src, dst)


def _degree_map(edges: List[Any]) -> Dict[str, int]:
    deg: Dict[str, int] = {}
    for e in edges:
        src, dst = _edge_endpoints(e)
        if src and src != dst:
            deg[src] = deg.get(src, 0) + 1
        if dst and src != dst:
            deg[dst] = deg.get(dst, 0) + 1
    return deg


def _top_hubs(nodes: List[Any], degree_map: Dict[str, int], limit: int) -> List[dict]:
    enriched = []
    for n in nodes:
        nid = _node_id(n)
        if not nid:
            continue
        name = n.get("name") or n.get("label") or nid
        enriched.append({"nodeId": nid, "nodeName": name, "degree": degree_map.get(nid, 0)})
    enriched.sort(key=lambda x: x["degree"], reverse=True)
    return enriched[:limit]


def _topic_coverage(nodes: List[Any]) -> List[dict]:
    counts: Dict[str, int] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        t = n.get("nodeTypeId") or n.get("typeId") or n.get("type")
        if not t:
            continue
        counts[t] = counts.get(t, 0) + 1
    return [{"typeName": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]


def _gaps(nodes: List[Any], degree_map: Dict[str, int], threshold: int, limit: int) -> List[dict]:
    out = []
    for n in nodes:
        nid = _node_id(n)
        if not nid:
            continue
        deg = degree_map.get(nid, 0)
        if deg < threshold:
            out.append({
                "nodeId": nid,
                "nodeName": n.get("name") or n.get("label") or nid,
                "degree": deg,
            })
    out.sort(key=lambda x: x["degree"])
    return out[:limit]


def _bfs_components(nodes: List[Any], edges: List[Any]) -> tuple[int, float]:
    node_set: set[str] = set()
    adj: Dict[str, List[str]] = {}
    for n in nodes:
        nid = _node_id(n)
        if nid and nid not in node_set:
            node_set.add(nid)
            adj.setdefault(nid, [])
    for e in edges:
        src, dst = _edge_endpoints(e)
        if src and dst and src != dst and src in node_set and dst in node_set:
            adj.setdefault(src, []).append(dst)
            adj.setdefault(dst, []).append(src)
    if not node_set:
        return 0, 0.0
    visited: set[str] = set()
    components = 0
    for start in node_set:
        if start in visited:
            continue
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for nb in adj.get(cur, []):
                if nb not in visited:
                    stack.append(nb)
        components += 1
    n = max(1, len(node_set))
    return components, round(components / n, 4)


async def _synthesize_recommendations(
    *,
    node_count: int,
    edge_count: int,
    important_nodes: List[dict],
    topic_coverage: List[dict],
    gaps: List[dict],
    fragmentation: float,
) -> str:
    template = render_prompt(
        "insights/recommendations.md",
        {
            "node_count": node_count,
            "edge_count": edge_count,
            "important_nodes": json.dumps(important_nodes, ensure_ascii=False, default=str),
            "topic_coverage": json.dumps(topic_coverage, ensure_ascii=False, default=str),
            "gaps_list": json.dumps(gaps, ensure_ascii=False, default=str),
            "fragmentation_ratio": f"{fragmentation:.2%}",
        },
    )
    try:
        model = get_chat_model(temperature=0.3)
        result = await model.ainvoke(template)
        return (result.content if hasattr(result, "content") else str(result)).strip()
    except Exception as e:  # ponystail: insights shouldn't block UI; degrade silently
        logger.warning(f"Recommendations LLM call failed: {e}")
        return (
            "### Structural Recommendations\n"
            "- Unable to generate AI recommendations at this time. "
            "The graph stats above are still accurate."
        )
