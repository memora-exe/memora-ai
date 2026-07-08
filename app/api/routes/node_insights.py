"""Phase 3 — AI Node Summary at 3 levels.

POST /api/node-insights/summary
Body: { node_id, project_id, jwt_token, level: beginner|intermediate|advanced }
Returns: { summary }

Reuses traverse_project_graph from graph_tools + ChatGoogleGenerativeAI.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.core.config import settings
from app.prompts.loader import load_prompt
from app.services.graph_tools import traverse_project_graph

router = APIRouter(prefix="/api/node-insights", tags=["AI Node Insights"])

VALID_LEVELS = {"beginner", "intermediate", "advanced"}
PROMPT_FILE = {
    "beginner": "node_summary_beginner.md",
    "intermediate": "node_summary_intermediate.md",
    "advanced": "node_summary_advanced.md",
}


class NodeSummaryRequest(BaseModel):
    node_id: str
    project_id: str
    jwt_token: str
    level: str = "intermediate"


def _format_neighbors(payload: Any) -> str:
    """Turn traverse result into a compact text block for the prompt."""
    if isinstance(payload, dict) and "error" in payload:
        return "(no neighbors available)"
    nodes = payload if isinstance(payload, list) else (payload.get("nodes") or [])
    if not nodes:
        return "(no neighbors)"
    lines: List[str] = []
    for n in nodes[:30]:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        label = n.get("label") or n.get("name") or nid
        ntype = n.get("type") or n.get("nodeType") or "?"
        lines.append(f"- {label} [{ntype}] (id={nid})")
    return "\n".join(lines)


def _format_node(payload: Any) -> Dict[str, str]:
    """Best-effort extraction of the central node from a traverse response."""
    if isinstance(payload, dict):
        if "node" in payload and isinstance(payload["node"], dict):
            n = payload["node"]
            return {
                "name": str(n.get("label") or n.get("name") or n.get("id") or ""),
                "type": str(n.get("type") or n.get("nodeType") or ""),
                "properties": str(n.get("properties") or ""),
            }
    return {"name": "", "type": "", "properties": ""}


@router.post("/summary")
async def node_summary(request: NodeSummaryRequest):
    if request.level not in VALID_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"level must be one of {sorted(VALID_LEVELS)}",
        )

    traversal = traverse_project_graph(
        project_id=request.project_id,
        jwt_token=request.jwt_token,
        start_node_id=request.node_id,
        depth=1,
    )
    if isinstance(traversal, dict) and "error" in traversal and not traversal.get("nodes"):
        raise HTTPException(status_code=502, detail=traversal["error"])

    node_info = _format_node(traversal)
    # Fallback: use node_id when label is missing
    if not node_info["name"]:
        node_info["name"] = request.node_id

    neighbors_text = _format_neighbors(traversal)

    template = load_prompt(PROMPT_FILE[request.level])
    prompt = (
        template.replace("{{node_name}}", node_info["name"])
        .replace("{{node_type}}", node_info["type"] or "(unknown)")
        .replace("{{node_properties}}", node_info["properties"] or "(none)")
        .replace("{{neighbors_text}}", neighbors_text)
    )

    llm = ChatGoogleGenerativeAI(
        model=settings.SUMMARY_MODEL,
        temperature=0.2,
        max_output_tokens=settings.NODE_SUMMARY_MAX_TOKENS,
    )
    response = await llm.ainvoke(prompt)
    summary = response.content if hasattr(response, "content") else str(response)

    return {"summary": summary, "level": request.level}