"""Phase 4 — Learning Navigator (Roadmaps) endpoints.

POST /api/roadmaps
Body: { project_id, jwt_token, topic?, fileIds?, depth? }
Returns: { topic, sourceFileIds, stages: [...] }

At least one of `topic` / `fileIds` is required. fileIds is capped server-side
at ROADMAP_MAX_FILE_IDS (Phase 4 hard pre-flight also runs in the BE).
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.roadmap_builder import build_roadmap

router = APIRouter(prefix="/api/roadmaps", tags=["Roadmaps"])


class RoadmapCreateReq(BaseModel):
    project_id: str
    jwt_token: str
    topic: Optional[str] = None
    fileIds: Optional[List[str]] = Field(default=None)
    depth: Optional[int] = None


@router.post("")
async def create_roadmap(body: RoadmapCreateReq):
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Roadmap build failed: {e}")

    return result
