from pydantic import BaseModel


class NodeSummaryRequest(BaseModel):
    node_id: str
    project_id: str
    jwt_token: str
    level: str = "intermediate"
