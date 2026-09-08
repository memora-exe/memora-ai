"""Phase 4 — Doc-aware topic extractor for the Learning Navigator (Roadmaps).

Reads already-ingested document_chunk rows (via chunk_repository) and asks
the configured LLM to pull out a topic + concepts.
"""
from __future__ import annotations

from typing import List

from app.common.logger.logger import get_logger
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.repositories.chunk_repository import load_chunk_text
from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json

logger = get_logger("DocumentTopicExtractor")


async def extract_topic_from_files(file_ids: List[str]) -> dict:
    """Return {"topic": str, "concepts": list[str]} parsed from LLM output."""
    combined_text = load_chunk_text(file_ids, settings.ROADMAP_DOC_TEXT_CHAR_BUDGET)
    if not combined_text.strip():
        return {"topic": "", "concepts": []}

    prompt = render_prompt(
        "document_topic_extraction.md",
        {
            "combined_text": combined_text,
            "max_concepts": "10",
        },
    )

    try:
        llm = get_chat_model(temperature=0.1)
        raw = await llm.ainvoke(prompt)
    except Exception as e:
        logger.warning(f"LLM call failed during doc topic extraction: {e}")
        return {"topic": "", "concepts": []}

    data = parse_llm_json(raw, fallback={})
    topic = str(data.get("topic", "") or "").strip()
    raw_concepts = data.get("concepts", []) or []
    concepts: list[str] = []
    for item in raw_concepts:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in concepts:
            concepts.append(cleaned)

    return {"topic": topic, "concepts": concepts}
