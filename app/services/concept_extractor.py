from __future__ import annotations

import asyncio
import re

from app.core.config import settings
from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json

PROMPT_INSTRUCTIONS = (
    "You are an expert Knowledge Graph Architect and Deep Domain Analyst.\n"
    "Analyze the following text thoroughly to extract deep conceptual nodes and semantic triples (subject, predicate, object) without using vector embeddings.\n\n"
    "Guidelines for Nodes / Entities:\n"
    "- Identify fundamental entities, mechanisms, theorems, architectural components, or core concepts.\n"
    "- Title must be canonical, concise, and standard.\n"
    "- Description must be precise, academically and technically rigorous, explaining mechanisms, properties, or role.\n"
    "- Provide relevant technical keywords and aliases.\n\n"
    "Guidelines for Semantic Triples / Relationships:\n"
    "- Extract knowledge as clean (subject, predicate, object) triples.\n"
    "- Classify predicate with strict semantic types:\n"
    "  * Hierarchical/Structural: PARENT_OF, PART_OF, SUBCLASS_OF\n"
    "  * Causal/Logical: CAUSES, LEADS_TO, RESOLVES\n"
    "  * Dependency: PREREQUISITE, DEPENDS_ON, REQUIRES\n"
    "  * Comparative/Contrast: CONTRASTS_WITH, SIMILAR_TO, ALTERNATIVE_TO\n"
    "  * Functional/Interaction: IMPLEMENTS, ENABLES, USES\n"
    "  * Associative/Contextual: RELATES_TO\n"
    "- Subject and object must match extracted node titles exactly.\n\n"
    "Return a JSON object with this exact structure:\n"
    "{\n"
    '  "nodes": [\n'
    '    {"title": "Concept Name", "description": "Rigorous technical description", "keywords": ["keyword1", "keyword2"], "aliases": ["alias1"], "confidence": 0.95}\n'
    "  ],\n"
    '  "triples": [\n'
    '    {"subject": "Concept A", "predicate": "PREREQUISITE", "object": "Concept B", "confidence": 0.9}\n'
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

    try:
        res = await asyncio.wait_for(
            llm.ainvoke(prompt),
            timeout=float(settings.INGESTION_LLM_TIMEOUT_SEC),
        )
        raw_content = getattr(res, "content", res)
        data = parse_llm_json(raw_content, fallback={})
        if isinstance(data, dict):
            # Normalize triples and edges
            if "triples" in data and not data.get("edges"):
                data["edges"] = [
                    {
                        "source": t.get("subject"),
                        "target": t.get("object"),
                        "type": t.get("predicate", "RELATES_TO"),
                        "confidence": t.get("confidence", 1.0),
                    }
                    for t in data["triples"]
                    if isinstance(t, dict) and t.get("subject") and t.get("object")
                ]
            elif "edges" in data and not data.get("triples"):
                data["triples"] = [
                    {
                        "subject": e.get("source"),
                        "predicate": e.get("type", "RELATES_TO"),
                        "object": e.get("target"),
                        "confidence": e.get("confidence", 1.0),
                    }
                    for e in data["edges"]
                    if isinstance(e, dict) and e.get("source") and e.get("target")
                ]

            if "nodes" in data or "edges" in data or "triples" in data:
                data.setdefault("nodes", [])
                data.setdefault("edges", [])
                data.setdefault("triples", [])
                return data
    except (asyncio.TimeoutError, TimeoutError):
        pass
    except Exception:
        pass

    return {"nodes": [], "edges": [], "triples": []}


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
