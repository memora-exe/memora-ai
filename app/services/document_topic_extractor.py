"""Extract roadmap topics from locally stored parsed documents."""
from __future__ import annotations

from typing import List

from app.common.logger.logger import get_logger
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.services.file_storage import read_full_text
from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json

logger = get_logger("DocumentTopicExtractor")


async def extract_topic_from_files(file_ids: List[str], project_id: str | None = None) -> dict:
    if not project_id:
        return {"topic": "", "concepts": []}
    combined_text = "\n\n".join(read_full_text(project_id, file_id) for file_id in file_ids)
    combined_text = combined_text[: settings.ROADMAP_DOC_TEXT_CHAR_BUDGET]
    if not combined_text.strip():
        return {"topic": "", "concepts": []}

    prompt = render_prompt("document_topic_extraction.md", {
        "combined_text": combined_text,
        "max_concepts": "10",
    })
    try:
        raw = await get_chat_model(temperature=0.1).ainvoke(prompt)
    except Exception as e:
        logger.warning(f"LLM call failed during doc topic extraction: {e}")
        return {"topic": "", "concepts": []}

    data = parse_llm_json(raw, fallback={})
    concepts = []
    for item in data.get("concepts", []) or []:
        if isinstance(item, str) and item.strip() and item.strip() not in concepts:
            concepts.append(item.strip())
    return {"topic": str(data.get("topic", "") or "").strip(), "concepts": concepts}
