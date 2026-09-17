"""File-based AI document search with graph node projection."""
from fastapi import APIRouter, Depends, HTTPException

from app.clients.graph_client import GraphClient
from app.core.dependencies import get_graph_client
from app.schemas.search import SearchRequest
from app.services.file_storage import grep_documents
from app.services.search.focal_area import compute_focal_area, project_to_search_shape

router = APIRouter(prefix="/api", tags=["AI Search"])


@router.post("/search")
async def ai_search(request: SearchRequest, graph_client: GraphClient = Depends(get_graph_client)):
    if not request.q or not request.q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")
    matches = grep_documents(request.project_id, request.q.strip())
    nodes_resp = await graph_client.get_nodes(request.project_id, request.jwt_token)
    nodes = nodes_resp if isinstance(nodes_resp, list) else (nodes_resp.get("data", []) if isinstance(nodes_resp, dict) else [])
    needle = request.q.casefold()
    matching_nodes = [n for n in nodes if isinstance(n, dict) and needle in str(n.get("label") or n.get("name") or "").casefold()]
    result = project_to_search_shape(matching_nodes)
    result["matches"] = matches
    result["focalArea"] = compute_focal_area(matching_nodes)
    return result
