from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    project_id: str
    jwt_token: str


class ChatResponse(BaseModel):
    reply: str
    tool_calls: Optional[dict] = None  # {citedNodes, citedEdges, chunks, reasoningPath}


class AutoTitleRequest(BaseModel):
    message: str
    project_id: str
    jwt_token: str = ""


class AutoTitleResponse(BaseModel):
    title: str
