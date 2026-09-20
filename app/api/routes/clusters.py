"""Semantic Community Detection router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from app.clients.graph_client import GraphClient
from app.core.dependencies import get_graph_client
from app.services.cluster_engine import detect_communities

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("")
async def get_project_clusters(
    project_id: str = Query(..., description="Project ID"),
    jwt_token: str = Query("", description="JWT Bearer token"),
    graph_client: GraphClient = Depends(get_graph_client),
):
    """Detect knowledge graph communities and return clusters with palette and nodes."""
    return await detect_communities(project_id, jwt_token, graph_client)
