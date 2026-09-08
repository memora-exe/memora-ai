"""Backward-compatibility shim — re-exports from new locations.

Will be deleted in Phase 6 after all importers are migrated.
"""
from app.services.search.hybrid_search import (
    hybrid_search as llm_hybrid_search,
    search_by_embedding as llm_search_by_embedding,
)
from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.core.config import settings
import asyncio

_gc = GraphClient(NestJSClient(settings.NESTJS_API_URL))


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def get_project_nodes(project_id: str, jwt_token: str) -> dict:
    return _run(_gc.get_nodes(project_id, jwt_token))


def get_project_edges(project_id: str, jwt_token: str) -> dict:
    return _run(_gc.get_edges(project_id, jwt_token))


def query_project_graph(project_id: str, jwt_token: str, query_params: dict) -> dict:
    return _run(_gc.query_graph(project_id, jwt_token, query_params))


def traverse_project_graph(project_id: str, jwt_token: str, start_node_id: str, depth: int = 3) -> dict:
    return _run(_gc.traverse_graph(project_id, jwt_token, start_node_id, depth))


def create_project_node(project_id: str, jwt_token: str, payload: dict) -> dict:
    return _run(_gc.create_node(project_id, jwt_token, payload))


def update_project_node(project_id: str, jwt_token: str, payload: dict) -> dict:
    return _run(_gc.update_node(project_id, jwt_token, payload))


def delete_project_node(project_id: str, jwt_token: str, node_id: str) -> dict:
    return _run(_gc.delete_node(project_id, jwt_token, node_id))


def create_project_edge(project_id: str, jwt_token: str, payload: dict) -> dict:
    return _run(_gc.create_edge(project_id, jwt_token, payload))


def update_project_edge(project_id: str, jwt_token: str, payload: dict) -> dict:
    return _run(_gc.update_edge(project_id, jwt_token, payload))


def delete_project_edge(project_id: str, jwt_token: str, edge_id: str) -> dict:
    return _run(_gc.delete_edge(project_id, jwt_token, edge_id))


def list_project_node_types(project_id: str, jwt_token: str) -> dict:
    return _run(_gc.get_node_types(project_id, jwt_token))


def list_project_files(project_id: str, jwt_token: str) -> dict:
    return _run(_gc.list_files(project_id, jwt_token))


def read_file_content(project_id: str, file_id: str, jwt_token: str) -> dict:
    return _run(_gc.read_file_content(file_id, jwt_token))


def llm_highlight_nodes(node_ids, **kwargs):
    cleaned = [str(n) for n in (node_ids or []) if n]
    return {"highlighted_nodes": cleaned, "_highlight": {"action": "highlighted", "kind": "nodes", "ids": cleaned}}


def llm_highlight_edges(edge_ids, **kwargs):
    cleaned = [str(e) for e in (edge_ids or []) if e]
    return {"highlighted_edges": cleaned, "_highlight": {"action": "highlighted", "kind": "edges", "ids": cleaned}}
