from pydantic import BaseModel


class DocSummaryRequest(BaseModel):
    file_id: str
    project_id: str
    jwt_token: str
    type: str = "short"
