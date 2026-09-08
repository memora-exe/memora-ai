"""Phase 3 — AI Graph Search.

POST /api/search
Body: { q, project_id, jwt_token }
Returns: { nodes, edges, focalArea: { cx, cy, zoom } }
"""
from fastapi import APIRouter, Depends, HTTPException

from app.clients.graph_client import GraphClient
from app.core.config import settings
from app.core.dependencies import get_embedding_service, get_graph_client
from app.schemas.search import SearchRequest
from app.services.embedding_service import EmbeddingService
from app.services.search.focal_area import compute_focal_area, project_to_search_shape
from app.services.search.hybrid_search import hybrid_search

router = APIRouter(prefix="/api", tags=["AI Search"])


@router.post("/search")
async def ai_search(
    request: SearchRequest,
    graph_client: GraphClient = Depends(get_graph_client),
    embedding_svc: EmbeddingService = Depends(get_embedding_service),
):
    if not request.q or not request.q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")

    result = hybrid_search(
        project_id=request.project_id,
        query=request.q,
        jwt_token=request.jwt_token,
        k=settings.SEARCH_TOP_K,
        graph_client=graph_client,
        embedding_service=embedding_svc,
    )

    if "error" in result and not result.get("nodes"):
        raise HTTPException(status_code=502, detail=result["error"])

    nodes = result.get("nodes") or []
    slim = project_to_search_shape(nodes)
    focal_area = compute_focal_area(nodes)

    return {**slim, "focalArea": focal_area}
