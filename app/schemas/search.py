from pydantic import BaseModel


class SearchRequest(BaseModel):
    q: str
    project_id: str
    jwt_token: str
