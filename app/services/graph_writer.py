"""Backward-compatibility shim — delegates to GraphClient.write_graph.

Will be deleted in Phase 6.
"""
import asyncio
from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import get_shared_nestjs_client
from app.core.config import settings

_gc = GraphClient(get_shared_nestjs_client())


def write_graph(project_id: str, jwt_token: str, graph_data: dict):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _gc.write_graph(project_id, jwt_token, graph_data)).result()
    return asyncio.run(_gc.write_graph(project_id, jwt_token, graph_data))
