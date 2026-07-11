"""Phase 4 — Doc-aware topic extractor for the Learning Navigator (Roadmaps).

Reads already-ingested document_chunk rows (no re-parse, no re-embed) and asks
the configured LLM to pull out a topic + 5–15 concept noun phrases suitable
for vector retrieval. Used when the roadmap request includes fileIds.
"""
from __future__ import annotations

import json
import re
from typing import List

from app.common.logger.logger import get_logger
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.services.llm import get_chat_model
from app.services.vector_store import get_db_connection

logger = get_logger("DocumentTopicExtractor")


def _load_chunk_text(file_ids: List[str], budget: int) -> str:
    """Concatenate chunk content across files, ordered by (file_id, chunk_index).
    Truncate to `budget` chars total — earliest chunks win on overflow."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Single round-trip: any-of file_ids, deterministic order.
            cur.execute(
                """
                SELECT file_id, chunk_index, content
                FROM document_chunk
                WHERE file_id = ANY(%s)
                ORDER BY file_id, chunk_index
                """,
                (file_ids,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    chunks: list[tuple[int, str]] = []
    for row in rows:
        content = row[2] or ""
        if not content:
            continue
        chunks.append((len(content), content))

    parts: list[str] = []
    remaining = budget
    for _size, content in chunks:
        if remaining <= 0:
            break
        if len(content) <= remaining:
            parts.append(content)
            remaining -= len(content)
        else:
            parts.append(content[:remaining])
            remaining = 0
    return "\n\n".join(parts)


async def extract_topic_from_files(file_ids: List[str]) -> dict:
    """Return {"topic": str, "concepts": list[str]} parsed from LLM output.

    On any LLM / parse failure, returns {"topic": "", "concepts": []} and logs
    a warning; the caller (roadmap_builder) is expected to continue gracefully
    using the user-supplied topic only.
    """
    combined_text = _load_chunk_text(file_ids, settings.ROADMAP_DOC_TEXT_CHAR_BUDGET)
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
        text = (raw.content if hasattr(raw, "content") else str(raw)).strip()
    except Exception as e:
        logger.warning(f"LLM call failed during doc topic extraction: {e}")
        return {"topic": "", "concepts": []}

    # Tolerate ```json ... ``` fences the model may add.
    match = re.search(r"\{[\s\S]*\}", text)
    payload = match.group(0) if match else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM JSON for doc topic: {e}; raw={text[:200]!r}")
        return {"topic": "", "concepts": []}

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
