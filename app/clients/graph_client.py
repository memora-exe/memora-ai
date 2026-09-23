"""Graph CRUD operations via NestJS backend — async, typed, no duplication.

Domain-specific wrapper over NestJSClient. Replaces graph_tools.py (13 HTTP
fns) and graph_writer.py (duplicate create_node/create_edge).
"""
from __future__ import annotations

from app.clients.nestjs_client import NestJSClient
from app.core.config import settings
from app.core.errors import GraphAPIError


def extract_node_id(node: dict) -> str | None:
    """Canonical node-id extraction — replaces 10+ inline repetitions."""
    return node.get("nodeId") or node.get("id") or node.get("elementId")


def extract_edge_endpoints(edge: dict) -> tuple[str | None, str | None]:
    """Canonical edge endpoint extraction."""
    src = edge.get("sourceNodeId") or edge.get("source") or edge.get("from")
    dst = edge.get("targetNodeId") or edge.get("target") or edge.get("to")
    return src, dst


class GraphClient:
    """Graph CRUD via NestJS backend. Async, typed, no duplication."""

    def __init__(self, client: NestJSClient):
        self._client = client

    # ── Nodes ─────────────────────────────────────────────────────────────

    async def get_nodes(self, project_id: str, jwt_token: str) -> list[dict]:
        return await self._client.get(
            f"/projects/{project_id}/graph/nodes", jwt_token
        )

    async def create_node(self, project_id: str, jwt_token: str, payload: dict) -> dict:
        return await self._client.post(
            f"/projects/{project_id}/graph/nodes", jwt_token, json=payload
        )

    async def update_node(self, project_id: str, jwt_token: str, payload: dict) -> dict:
        return await self._client.patch(
            f"/projects/{project_id}/graph/nodes", jwt_token, json=payload
        )

    async def delete_node(self, project_id: str, jwt_token: str, node_id: str) -> dict:
        await self._client.delete(
            f"/projects/{project_id}/graph/nodes/{node_id}", jwt_token
        )
        return {"success": True, "nodeId": node_id}

    # ── Edges ─────────────────────────────────────────────────────────────

    async def get_edges(self, project_id: str, jwt_token: str) -> list[dict]:
        return await self._client.get(
            f"/projects/{project_id}/graph/edges", jwt_token
        )

    async def create_edge(self, project_id: str, jwt_token: str, payload: dict) -> dict:
        return await self._client.post(
            f"/projects/{project_id}/graph/edges", jwt_token, json=payload
        )

    async def update_edge(self, project_id: str, jwt_token: str, payload: dict) -> dict:
        return await self._client.patch(
            f"/projects/{project_id}/graph/edges", jwt_token, json=payload
        )

    async def delete_edge(self, project_id: str, jwt_token: str, edge_id: str) -> dict:
        await self._client.delete(
            f"/projects/{project_id}/graph/edges/{edge_id}", jwt_token
        )
        return {"success": True, "edgeId": edge_id}

    # ── Query / Traverse ──────────────────────────────────────────────────

    async def query_graph(self, project_id: str, jwt_token: str, query_params: dict) -> dict:
        return await self._client.post(
            f"/projects/{project_id}/graph/query", jwt_token, json=query_params
        )

    async def traverse_graph(
        self, project_id: str, jwt_token: str, start_node_id: str, depth: int = 3
    ) -> dict:
        # ponytail: defensive guard against LLM hallucinating "None"/"null"/empty ids
        if start_node_id is None or str(start_node_id).strip() in ("", "None", "null"):
            return {"error": "missing start_node_id", "nodes": [], "edges": []}
        return await self._client.get(
            f"/projects/{project_id}/graph/traverse/{start_node_id}",
            jwt_token,
            params={"depth": depth},
        )

    async def find_path(
        self, project_id: str, jwt_token: str, source: str, target: str, max_depth: int = 6
    ) -> dict:
        if not source or not target:
            return {"error": "source and target must be non-empty", "nodes": [], "edges": [], "bridgeNodes": []}
        return await self._client.get(
            f"/projects/{project_id}/graph/path",
            jwt_token,
            params={"source": source, "target": target, "maxDepth": max_depth},
        )

    # ── Clusters ──────────────────────────────────────────────────────────

    async def get_clusters(self, project_id: str, jwt_token: str) -> dict:
        return await self._client.get(
            f"/projects/{project_id}/graph/clusters", jwt_token
        )

    async def create_cluster(
        self, project_id: str, jwt_token: str, payload: dict
    ) -> dict:
        return await self._client.post(
            f"/projects/{project_id}/graph/clusters", jwt_token, json=payload
        )

    async def add_node_to_cluster(
        self, project_id: str, jwt_token: str, cluster_id: str, node_id: str
    ) -> dict:
        return await self._client.post(
            f"/projects/{project_id}/graph/clusters/{cluster_id}/nodes",
            jwt_token,
            json={"nodeId": node_id},
        )

    async def remove_node_from_cluster(
        self, project_id: str, jwt_token: str, cluster_id: str, node_id: str
    ) -> dict:
        await self._client.delete(
            f"/projects/{project_id}/graph/clusters/{cluster_id}/nodes/{node_id}",
            jwt_token,
        )
        return {"success": True, "clusterId": cluster_id, "nodeId": node_id}

    # ── Node types ────────────────────────────────────────────────────────

    async def get_node_types(self, project_id: str, jwt_token: str) -> list[dict]:
        return await self._client.get(
            f"/projects/{project_id}/graph/node-types", jwt_token
        )

    # ── Files ─────────────────────────────────────────────────────────────

    async def list_files(self, project_id: str, jwt_token: str) -> list[dict]:
        return await self._client.get(
            f"/files/project/{project_id}", jwt_token, timeout=30.0
        )

    async def read_file_content(self, file_id: str, jwt_token: str) -> dict:
        return await self._client.get(
            f"/files/{file_id}/content", jwt_token, timeout=60.0
        )

    async def download_file(self, file_key: str, jwt_token: str) -> bytes:
        """Download raw file bytes — used by ingestion pipeline."""
        url = f"{self._client._base_url}/files/download/{file_key}"
        headers = {}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        if settings.MEMORA_INTERNAL_TOKEN:
            headers["X-Internal-Token"] = settings.MEMORA_INTERNAL_TOKEN
        try:
            res = await self._client.http_client.get(url, headers=headers, timeout=120.0)
            res.raise_for_status()
            return res.content
        except Exception as e:
            raise GraphAPIError(f"download {file_key} failed: {e}") from e

    # ── Batch graph write (used by ingestion pipeline) ────────────────────

    async def batch_write_graph(self, project_id: str, jwt_token: str, graph_data: dict) -> dict:
        """Write nodes and edges in a single batch request, fallback to individual if needed."""
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])

        nodes_payload = []
        for node in nodes:
            name = node.get("title")
            if not name:
                continue
            nodes_payload.append({
                "nodeName": name,
                "data": {
                    "description": node.get("description", ""),
                    "keywords": node.get("keywords", []),
                    "aliases": node.get("aliases", []),
                    "confidence": node.get("confidence", 1.0),
                },
            })

        edges_payload = []
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                continue
            edges_payload.append({
                "sourceNodeId": source,
                "targetNodeId": target,
                "properties": {
                    "type": edge.get("type", "RELATED_TO"),
                    "confidence": edge.get("confidence", 1.0),
                },
            })

        if not nodes_payload and not edges_payload:
            return {"createdNodes": 0, "createdEdges": 0, "nodeIdMap": {}}

        payload = {"nodes": nodes_payload, "edges": edges_payload}
        internal_token = settings.MEMORA_INTERNAL_TOKEN

        # Primary route: Internal token endpoint (bypasses expired/missing user JWT)
        if internal_token:
            try:
                res = await self._client.internal_post(
                    f"/internal/projects/{project_id}/graph/batch",
                    internal_token,
                    json=payload,
                    timeout=60.0,
                )
                return res if isinstance(res, dict) else {}
            except Exception as e:
                from app.common.logger.logger import get_logger
                get_logger("GraphClient").warning(
                    f"batch_write_graph internal endpoint failed: {e}"
                )
                # If auth error (401/403), do not fallback to sequential writes with bad auth
                status = getattr(e, "status_code", None)
                if status in (401, 403):
                    raise

        # Secondary route: Authenticated endpoint via JWT if internal token not available or failed
        if jwt_token:
            try:
                res = await self._client.post(
                    f"/projects/{project_id}/graph/batch",
                    jwt_token,
                    json=payload,
                    timeout=60.0,
                )
                return res if isinstance(res, dict) else {}
            except Exception as e:
                from app.common.logger.logger import get_logger
                get_logger("GraphClient").warning(
                    f"batch_write_graph JWT endpoint failed: {e}"
                )
                status = getattr(e, "status_code", None)
                if status in (401, 403):
                    raise
                # Fallback to sequential individual writes only for non-auth errors
                await self.write_graph(project_id, jwt_token, graph_data)
                return {
                    "createdNodes": len(nodes_payload),
                    "createdEdges": len(edges_payload),
                    "nodeIdMap": {},
                }

        raise GraphAPIError("No valid internal token or JWT provided for batch_write_graph")


    async def write_graph(self, project_id: str, jwt_token: str, graph_data: dict) -> None:
        """Write nodes and edges from concept extraction. Replaces graph_writer.py."""
        node_map: dict[str, str] = {}

        for node in graph_data.get("nodes", []):
            name = node.get("title")
            if not name:
                continue
            payload = {
                "nodeName": name,
                "data": {
                    "description": node.get("description", ""),
                    "keywords": node.get("keywords", []),
                    "aliases": node.get("aliases", []),
                    "confidence": node.get("confidence", 1.0),
                },
            }
            try:
                result = await self.create_node(project_id, jwt_token, payload)
                node_id = result.get("nodeId") if isinstance(result, dict) else None
                if node_id:
                    node_map[name.lower()] = node_id
            except GraphAPIError as e:
                # Log and continue — don't break the whole pipeline
                from app.common.logger.logger import get_logger
                get_logger("GraphClient").warning(f"write_graph node creation failed: {e}")

        for edge in graph_data.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                continue
            source_id = node_map.get(source.lower())
            target_id = node_map.get(target.lower())
            if not source_id or not target_id:
                continue
            payload = {
                "sourceNodeId": source_id,
                "targetNodeId": target_id,
                "properties": {
                    "type": edge.get("type", "RELATED_TO"),
                    "confidence": edge.get("confidence", 1.0),
                },
            }
            try:
                await self.create_edge(project_id, jwt_token, payload)
            except GraphAPIError as e:
                from app.common.logger.logger import get_logger
                get_logger("GraphClient").warning(f"write_graph edge creation failed: {e}")
