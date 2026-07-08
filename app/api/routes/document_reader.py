"""Phase 3 — AI Document Reader (5 summary formats).

POST /api/document-reader/summary
Body: { file_id, project_id, jwt_token, type: short|detailed|executive|keyPoints|timeline }
Returns: { summary }
"""
from typing import List

from fastapi import APIRouter, HTTPException
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.core.config import settings
from app.prompts.loader import load_prompt
from app.services.vector_store import get_db_connection

router = APIRouter(prefix="/api/document-reader", tags=["AI Document Reader"])

VALID_TYPES = {"short", "detailed", "executive", "keyPoints", "timeline"}
PROMPT_FILE = {
    "short": "doc_short_summary.md",
    "detailed": "doc_detailed_summary.md",
    "executive": "doc_executive_summary.md",
    "keyPoints": "doc_key_points.md",
    "timeline": "doc_timeline.md",
}


class DocSummaryRequest(BaseModel):
    file_id: str
    project_id: str
    jwt_token: str
    type: str = "short"


def _fetch_chunks(file_id: str) -> List[str]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_index, content FROM document_chunk "
                "WHERE file_id = %s ORDER BY chunk_index",
                (file_id,),
            )
            rows = cur.fetchall()
        return [r[1] for r in rows if r[1]]
    finally:
        conn.close()


@router.post("/summary")
async def document_summary(request: DocSummaryRequest):
    if request.type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of {sorted(VALID_TYPES)}",
        )

    try:
        chunks = _fetch_chunks(request.file_id)
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

    llm = ChatGoogleGenerativeAI(
        model=settings.SUMMARY_MODEL,
        temperature=0.1,
        max_output_tokens=settings.DOC_SUMMARY_MAX_TOKENS,
    )
    response = await llm.ainvoke(prompt)
    summary = response.content if hasattr(response, "content") else str(response)

    return {"summary": summary, "type": request.type}