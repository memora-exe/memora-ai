"""Phase 4 — Knowledge Insights Dashboard endpoint.

GET /api/insights?project_id=<id>&jwt_token=<token>
Returns structural analytics + LLM-generated recommendations.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.graph_client import GraphClient
from app.core.dependencies import get_graph_client
from app.services.insights_engine import compute_insights

router = APIRouter(prefix="/api/insights", tags=["Insights"])


@router.get("")
async def get_insights(
    project_id: str = Query(...),
    jwt_token: str | None = Query(default=None),
    graph_client: GraphClient = Depends(get_graph_client),
):
    if not project_id:
        raise HTTPException(status_code=400, detail="`project_id` is required.")
    try:
        return await compute_insights(
            project_id=project_id,
            jwt_token=jwt_token,
            graph_client=graph_client,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insights computation failed: {e}")
