from fastapi import APIRouter
from app.api.routes.chat import router as chat_router
from app.api.routes.search import router as search_router
from app.api.routes.node_insights import router as node_insights_router
from app.api.routes.document_reader import router as document_reader_router
from app.api.routes.roadmap import router as roadmap_router
from app.api.routes.insights import router as insights_router
from app.api.routes.prompts import router as prompts_router
from app.api.routes.clusters import router as clusters_router
from app.api.routes.flashcards import router as flashcards_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(search_router)
router.include_router(node_insights_router)
router.include_router(document_reader_router)
router.include_router(roadmap_router)
router.include_router(insights_router)
router.include_router(prompts_router)
router.include_router(clusters_router)
router.include_router(flashcards_router)