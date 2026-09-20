"""NetworkX Louvain Community Detection & Semantic Topic Labeling Engine.

Detects densely connected communities in project knowledge graphs and generates
descriptive cluster labels with assigned semantic colors.
"""
from __future__ import annotations

import logging
from typing import Any

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore

from app.clients.graph_client import GraphClient, extract_node_id, extract_edge_endpoints

logger = logging.getLogger(__name__)

CLUSTER_PALETTE = [
    "#3B82F6",  # Electric Blue
    "#10B981",  # Emerald Green
    "#F59E0B",  # Amber / Warm Gold
    "#EF4444",  # Crimson Red
    "#8B5CF6",  # Deep Purple
    "#EC4899",  # Vivid Pink
    "#14B8A6",  # Teal Cyan
    "#F97316",  # Vibrant Orange
    "#06B6D4",  # Sky Cyan
    "#84CC16",  # Lime Green
]


def _derive_cluster_topic(
    member_nodes: list[dict[str, Any]],
    subgraph_degrees: dict[str, int] | None = None,
) -> str:
    """Derive an informative topic label for a cluster.

    Picks top representative concepts using internal node degree (centrality)
    or note keywords rather than simple arbitrary slicing.
    """
    if not member_nodes:
        return "General Concepts"

    degrees = subgraph_degrees or {}
    sorted_nodes = sorted(
        member_nodes,
        key=lambda n: (degrees.get(n.get("id", ""), 0), len(n.get("note", ""))),
        reverse=True,
    )

    clean_names = [n["name"].strip() for n in sorted_nodes if n.get("name", "").strip()]
    if not clean_names:
        return "General Concepts"
    if len(clean_names) == 1:
        return clean_names[0]
    if len(clean_names) == 2:
        return f"{clean_names[0]} & {clean_names[1]}"

    top_names = clean_names[:2]
    return f"{' & '.join(top_names)} (+{len(clean_names) - 2} concepts)"


async def detect_communities(
    project_id: str,
    jwt_token: str,
    graph_client: GraphClient,
) -> dict:
    """Run Louvain community detection on the project graph with modularity scoring."""
    logger.info("Detecting communities for project %s", project_id)

    try:
        nodes = await graph_client.get_nodes(project_id, jwt_token)
        edges = await graph_client.get_edges(project_id, jwt_token)
    except Exception as exc:
        logger.warning("Failed to fetch graph data for clustering: %s", exc)
        return {"clusters": [], "totalClusters": 0, "modularity": 0.0}

    if not nodes:
        return {"clusters": [], "totalClusters": 0, "modularity": 0.0}

    # Graceful fallback if networkx is missing
    if nx is None:
        logger.warning("networkx not installed; using basic connected component fallback")
        node_ids = [extract_node_id(n) for n in nodes if extract_node_id(n)]
        clusters = [
            {
                "clusterId": "cluster_1",
                "name": "General Cluster",
                "color": CLUSTER_PALETTE[0],
                "nodeIds": node_ids,
                "size": len(node_ids),
            }
        ]
        return {"clusters": clusters, "totalClusters": 1, "modularity": 0.0}

    # 1. Build NetworkX Undirected Graph
    G = nx.Graph()
    node_meta_map: dict[str, dict[str, Any]] = {}

    for n in nodes:
        nid = extract_node_id(n)
        if nid:
            name = n.get("nodeName") or nid
            note = n.get("note") or ""
            node_meta_map[nid] = {"id": nid, "name": name, "note": note}
            G.add_node(nid, name=name, note=note)

    for e in edges:
        src, dst = extract_edge_endpoints(e)
        if src and dst and G.has_node(src) and G.has_node(dst):
            G.add_edge(src, dst)

    if G.number_of_nodes() == 0:
        return {"clusters": [], "totalClusters": 0, "modularity": 0.0}

    # 2. Community Detection: Louvain on connected components or full graph
    communities: list[set] = []
    modularity_score: float = 0.0

    if G.number_of_edges() > 0:
        try:
            communities = list(nx.community.louvain_communities(G, seed=42))
            try:
                modularity_score = float(nx.community.modularity(G, communities))
            except Exception:
                modularity_score = 0.0
        except Exception as exc:
            logger.warning("Louvain algorithm failed (%s); fallback to connected components", exc)
            communities = list(nx.connected_components(G))
            try:
                modularity_score = float(nx.community.modularity(G, communities))
            except Exception:
                modularity_score = 0.0
    else:
        # Isolated nodes without edges: each node in its own cluster or grouped into 1
        communities = [set([n]) for n in G.nodes]
        modularity_score = 0.0

    # Sort communities by size descending
    communities.sort(key=lambda c: len(c), reverse=True)

    # 3. Format clusters with palette and topic names
    clusters = []
    for idx, comm in enumerate(communities):
        node_ids = list(comm)
        color = CLUSTER_PALETTE[idx % len(CLUSTER_PALETTE)]
        member_nodes = [node_meta_map.get(nid, {"id": nid, "name": nid, "note": ""}) for nid in node_ids]
        subgraph = G.subgraph(node_ids)
        subgraph_degrees = dict(subgraph.degree()) if hasattr(subgraph, "degree") else {}
        topic_name = _derive_cluster_topic(member_nodes, subgraph_degrees)

        clusters.append(
            {
                "clusterId": f"cluster_{idx + 1}",
                "name": topic_name,
                "color": color,
                "nodeIds": node_ids,
                "size": len(node_ids),
            }
        )

    return {
        "clusters": clusters,
        "totalClusters": len(clusters),
        "modularity": round(modularity_score, 4),
    }
