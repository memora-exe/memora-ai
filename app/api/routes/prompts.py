"""Phase 4 — Prompt Library seeds endpoint.

GET /api/prompts/system-seeds
Returns the markdown templates shipped in app/prompts/library/*.md,
parsed into {name, category, template}. The NestJS PromptLibraryService
upserts these into PostgreSQL on boot so they're available to users.
"""
from fastapi import APIRouter

from app.db.prompt_seeds import get_system_prompts

router = APIRouter(prefix="/api/prompts", tags=["Prompts"])


@router.get("/system-seeds")
async def list_system_seeds():
    return get_system_prompts()
