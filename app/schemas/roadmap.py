from typing import List, Optional

from pydantic import BaseModel, Field


class RoadmapCreateReq(BaseModel):
    project_id: str
    jwt_token: str
    topic: Optional[str] = None
    fileIds: Optional[List[str]] = Field(default=None)
    depth: Optional[int] = None
