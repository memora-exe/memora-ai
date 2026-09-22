from __future__ import annotations

import asyncio
import re

from app.core.config import settings
from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json

PROMPT_INSTRUCTIONS = (
    "You are an expert Knowledge Graph Architect and Deep Domain Analyst.\n"
    "Analyze the following text thoroughly to extract deep conceptual nodes and multidimensional semantic relationships.\n\n"
    "Guidelines for Nodes:\n"
    "- Identify fundamental entities, mechanisms, theorems, architectural components, or core concepts.\n"
    "- Title must be canonical, concise, and standard.\n"
    "- Description must be precise, academically and technically rigorous, explaining mechanisms, properties, or role.\n"
    "- Provide relevant technical keywords and aliases.\n\n"
    "Guidelines for Edges (Relationships):\n"
    "- Classify relationships with strict semantic types:\n"
    "  * Hierarchical/Structural: PARENT_OF, PART_OF, SUBCLASS_OF\n"
    "  * Causal/Logical: CAUSES, LEADS_TO, RESOLVES\n"
    "  * Dependency: PREREQUISITE, DEPENDS_ON, REQUIRES\n"
    "  * Comparative/Contrast: CONTRASTS_WITH, SIMILAR_TO, ALTERNATIVE_TO\n"
    "  * Functional/Interaction: IMPLEMENTS, ENABLES, USES\n"
    "  * Associative/Contextual: RELATES_TO\n"
    "- Source and target must match extracted node titles exactly.\n\n"
    "Return a JSON object with this exact structure:\n"
    "{\n"
    '  "nodes": [\n'
    '    {"title": "Concept Name", "description": "Rigorous technical description", "keywords": ["keyword1", "keyword2"], "aliases": ["alias1"], "confidence": 0.95}\n'
    "  ],\n"
    '  "edges": [\n'
    '    {"source": "Concept A", "target": "Concept B", "type": "PREREQUISITE", "confidence": 0.9}\n'
    "  ]\n"
    "}\n"
    "Ensure the output is valid JSON and nothing else.\n"
    "Text:\n"
)


async def aextract_concepts(text: str) -> dict:
    """Async concept extraction using ainvoke and temperature=0.0."""
    llm = get_chat_model(temperature=0.0)
    capped_text = text[: settings.INGESTION_TEXT_CHAR_CAP]
    prompt = PROMPT_INSTRUCTIONS + capped_text

    for _ in range(2):
        try:
            res = await asyncio.wait_for(
                llm.ainvoke(prompt),
                timeout=float(settings.INGESTION_LLM_TIMEOUT_SEC),
            )
            raw_content = getattr(res, "content", res)
            data = parse_llm_json(raw_content, fallback={})
            if "nodes" in data and "edges" in data:
                return data
        except Exception:
            continue

    return {"nodes": [], "edges": []}


def extract_concepts(text: str) -> dict:
    """Synchronous wrapper for backward compatibility."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, aextract_concepts(text)).result()
        return loop.run_until_complete(aextract_concepts(text))
    except Exception:
        return {"nodes": [], "edges": []}
