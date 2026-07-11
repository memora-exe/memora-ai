from pydantic import BaseModel
from typing import Optional, List, Any

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    project_id: str
    jwt_token: str

class ChatResponse(BaseModel):
    reply: str
    tool_calls: Optional[dict] = None  # {citedNodes, citedEdges, chunks, reasoningPath}
