"""Phase 4 — Learning Navigator (Roadmaps) endpoints.

POST /api/roadmaps
Body: { project_id, jwt_token, topic?, fileIds?, depth? }
Returns: { topic, sourceFileIds, stages: [...] }
"""
from fastapi import APIRouter, Depends, HTTPException

from app.clients.graph_client import GraphClient
from app.core.config import settings
from app.core.dependencies import get_graph_client
from app.schemas.roadmap import RoadmapCreateReq
from app.services.roadmap_builder import build_roadmap

router = APIRouter(prefix="/api/roadmaps", tags=["Roadmaps"])


@router.post("")
async def create_roadmap(
    body: RoadmapCreateReq,
    graph_client: GraphClient = Depends(get_graph_client),
):
    has_topic = bool(body.topic and body.topic.strip())
    has_files = bool(body.fileIds)

    if not has_topic and not has_files:
        raise HTTPException(
            status_code=400,
            detail="At least one of `topic` or `fileIds` must be provided.",
        )

    file_ids = body.fileIds or []
    if len(file_ids) > settings.ROADMAP_MAX_FILE_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"fileIds length ({len(file_ids)}) exceeds ROADMAP_MAX_FILE_IDS "
                   f"({settings.ROADMAP_MAX_FILE_IDS}).",
        )

    try:
        result = await build_roadmap(
            project_id=body.project_id,
            topic=body.topic,
            file_ids=file_ids,
            depth=body.depth,
            jwt_token=body.jwt_token,
            graph_client=graph_client,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Roadmap build failed: {e}")

    return result
