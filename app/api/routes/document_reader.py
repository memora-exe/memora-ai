"""Phase 3 — AI Document Reader (5 summary formats).

POST /api/document-reader/summary
Body: { file_id, project_id, jwt_token, type: short|detailed|executive|keyPoints|timeline }
Returns: { summary }
"""
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.prompts.loader import load_prompt
from app.repositories.chunk_repository import fetch_chunks_by_file
from app.schemas.document_reader import DocSummaryRequest
from app.services.llm import get_chat_model

router = APIRouter(prefix="/api/document-reader", tags=["AI Document Reader"])

VALID_TYPES = {"short", "detailed", "executive", "keyPoints", "timeline"}
PROMPT_FILE = {
    "short": "doc_short_summary.md",
    "detailed": "doc_detailed_summary.md",
    "executive": "doc_executive_summary.md",
    "keyPoints": "doc_key_points.md",
    "timeline": "doc_timeline.md",
}


@router.post("/summary")
async def document_summary(request: DocSummaryRequest):
    if request.type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of {sorted(VALID_TYPES)}",
        )

    try:
        chunks = fetch_chunks_by_file(request.file_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DB read failed: {e}")

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No chunks found for this file. Has it been processed?",
        )

    text = "\n\n".join(chunks)
    cap = settings.DOC_SUMMARY_INPUT_CAP
    if len(text) > cap:
        text = text[:cap] + "\n\n[...truncated for summarization...]"

    template = load_prompt(PROMPT_FILE[request.type])
    prompt = template.replace("{{document_text}}", text)

    llm = get_chat_model(temperature=0.1)
    response = await llm.ainvoke(prompt)
    summary = response.content if hasattr(response, "content") else str(response)

    return {"summary": summary, "type": request.type}
