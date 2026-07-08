from fastapi import APIRouter
from app.api.routes.chat import router as chat_router
from app.api.routes.search import router as search_router
from app.api.routes.node_insights import router as node_insights_router
from app.api.routes.document_reader import router as document_reader_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(search_router)
router.include_router(node_insights_router)
router.include_router(document_reader_router)