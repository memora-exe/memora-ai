from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    project_id: str
    jwt_token: str

class ChatResponse(BaseModel):
    reply: str
