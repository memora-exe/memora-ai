"""GraphRAG context retrieval engine: non-vector seed match + 1-2 hops traversal."""
from __future__ import annotations

from typing import Any
from rapidfuzz import fuzz

from app.clients.graph_client import GraphClient, extract_edge_endpoints, extract_node_id
from app.clients.nestjs_client import NestJSClient, get_shared_nestjs_client
from app.common.logger.logger import get_logger

logger = get_logger("GraphRagRetriever")


def serialize_graphrag_markdown(
    seeds: list[dict[str, Any]],
    subgraph_nodes: list[dict[str, Any]],
    subgraph_edges: list[dict[str, Any]],
    query: str = "",
) -> str:
    """Serialize seeds and 1-2 hops subgraph into standard Markdown context."""
    lines = ["### Knowledge Graph Context"]

    # 1. Matched Seed Entities
    lines.append("#### Matched Seed Entities:")
    if not seeds:
        lines.append("- *(No direct seed entity matches found)*")
    else:
        for s in seeds:
            name = s.get("nodeName") or s.get("title") or s.get("name") or "Unknown"
            nid = extract_node_id(s) or s.get("nodeId") or "unknown"
            note = s.get("note") or ""
            if not note and isinstance(s.get("data"), dict):
                note = s["data"].get("description", "")
            note_str = str(note).strip()
            excerpt = (note_str[:160] + "...") if len(note_str) > 160 else (note_str or "No note available")
            lines.append(f"- **{name}** (ID: {nid}): {excerpt}")

    # Build node id -> display name map
    node_name_map: dict[str, str] = {}
    for n in [*seeds, *subgraph_nodes]:
        nid = extract_node_id(n) or n.get("nodeId")
        name = n.get("nodeName") or n.get("title") or n.get("name")
        if nid and name:
            node_name_map[str(nid)] = str(name)

    # 2. Connected Subgraph (1-2 Hops)
    lines.append("#### Connected Subgraph (1-2 Hops):")
    if not subgraph_edges:
        lines.append("- *(No connected relationships found within 1-2 hops)*")
    else:
        seen_edges = set()
        for e in subgraph_edges:
            src, dst = extract_edge_endpoints(e)
            src_str = str(src or "")
            dst_str = str(dst or "")
            if not src_str or not dst_str:
                continue

            src_name = node_name_map.get(src_str, src_str)
            dst_name = node_name_map.get(dst_str, dst_str)

            props = e.get("properties") or {}
            is_mention = False
            if isinstance(props, dict):
                is_mention = bool(props.get("isMention"))
            elif isinstance(props, str) and '"isMention":true' in props:
                is_mention = True

            if is_mention:
                edge_desc = "{isMention: true}"
            else:
                pred = (
                    e.get("predicate")
                    or e.get("edgeTypeId")
                    or e.get("type")
                    or (props.get("type") if isinstance(props, dict) else None)
                    or "RELATES_TO"
                )
                edge_desc = f'{{predicate: "{pred}"}}'

            edge_line = f"- ({src_name}) -[:RELATES_TO {edge_desc}]-> ({dst_name})"
            if edge_line not in seen_edges:
                seen_edges.add(edge_line)
                lines.append(edge_line)

    return "\n".join(lines)


class GraphRagRetriever:
    """Non-vector GraphRAG context retriever using seed match and 1-2 hops traversal."""

    def __init__(
        self,
        nestjs_client: NestJSClient | None = None,
        graph_client: GraphClient | None = None,
    ):
        self._nestjs_client = nestjs_client or get_shared_nestjs_client()
        self._graph_client = graph_client or GraphClient(self._nestjs_client)

    async def retrieve_context(
        self,
        project_id: str,
        query: str,
        jwt_token: str = "",
        max_hops: int = 2,
        max_seeds: int = 5,
    ) -> dict[str, Any]:
        """Retrieve local graph context for a query without vector embeddings.

        Tries backend /search/graphrag endpoint first. If unavailable, falls back
        to direct seed fuzzy matching and REST traversal.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            empty_md = serialize_graphrag_markdown([], [], [], query="")
            return {
                "seeds": [],
                "subgraphNodes": [],
                "subgraphEdges": [],
                "serializedMarkdown": empty_md,
            }

        # 1. Try Backend GraphRAG Endpoint
        try:
            backend_res = await self._nestjs_client.get(
                f"/projects/{project_id}/search/graphrag",
                jwt_token,
                params={"q": clean_query, "maxHops": max_hops, "maxSeeds": max_seeds},
            )
            if isinstance(backend_res, dict) and "serializedMarkdown" in backend_res:
                return backend_res
        except Exception as e:
            logger.debug(f"BE graphrag endpoint not available or failed: {e}. Falling back to graph client.")

        # 2. Fallback: Local GraphClient seed search & traversal
        all_nodes = await self._graph_client.get_nodes(project_id, jwt_token)
        if not isinstance(all_nodes, list):
            all_nodes = []

        # Score nodes against query using RapidFuzz
        scored_seeds: list[tuple[float, dict[str, Any]]] = []
        for node in all_nodes:
            if not isinstance(node, dict):
                continue
            name = str(node.get("nodeName") or node.get("title") or node.get("name") or "")
            note = str(node.get("note") or "")
            name_score = fuzz.token_set_ratio(clean_query, name)
            note_score = fuzz.partial_ratio(clean_query, note) if note else 0.0
            combined_score = max(name_score, note_score * 0.8)
            if combined_score > 35.0:
                scored_seeds.append((combined_score, node))

        scored_seeds.sort(key=lambda x: x[0], reverse=True)
        seeds = [node for _, node in scored_seeds[:max_seeds]]

        # Traverse 1-2 hops for seeds
        subgraph_nodes_map: dict[str, dict[str, Any]] = {}
        subgraph_edges: list[dict[str, Any]] = []
        seen_edge_ids = set()

        for s in seeds:
            sid = extract_node_id(s)
            if not sid:
                continue
            try:
                trav = await self._graph_client.traverse_graph(
                    project_id, jwt_token, sid, depth=min(max_hops, 2)
                )
                if isinstance(trav, dict):
                    for n in trav.get("nodes", []):
                        nid = extract_node_id(n)
                        if nid and nid not in subgraph_nodes_map:
                            subgraph_nodes_map[nid] = n
                    for e in trav.get("edges", []):
                        eid = e.get("edgeId") or f"{extract_edge_endpoints(e)}"
                        if eid not in seen_edge_ids:
                            seen_edge_ids.add(eid)
                            subgraph_edges.append(e)
            except Exception as e:
                logger.debug(f"Traversal failed for seed {sid}: {e}")

        subgraph_nodes = list(subgraph_nodes_map.values())
        serialized_md = serialize_graphrag_markdown(
            seeds=seeds,
            subgraph_nodes=subgraph_nodes,
            subgraph_edges=subgraph_edges,
            query=clean_query,
        )

        return {
            "seeds": seeds,
            "subgraphNodes": subgraph_nodes,
            "subgraphEdges": subgraph_edges,
            "serializedMarkdown": serialized_md,
        }
