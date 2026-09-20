"""Flashcard Generation router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.clients.graph_client import GraphClient
from app.core.dependencies import get_graph_client
from app.services.flashcard_generator import generate_flashcards_from_nodes

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])


class GenerateFlashcardsRequest(BaseModel):
    project_id: str
    node_ids: list[str] = Field(default_factory=list)
    count: int = Field(default=8, ge=1, le=20)
    jwt_token: str = Field(default="")


@router.post("/generate")
async def generate_flashcards(
    req: GenerateFlashcardsRequest,
    graph_client: GraphClient = Depends(get_graph_client),
):
    """Generate structured flashcards from graph nodes using pedagogical heuristics."""
    cards = await generate_flashcards_from_nodes(
        project_id=req.project_id,
        node_ids=req.node_ids,
        count=req.count,
        jwt_token=req.jwt_token,
        graph_client=graph_client,
    )
    return {"cards": cards, "total": len(cards)}
