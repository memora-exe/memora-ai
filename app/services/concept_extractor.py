import json
import re
from app.core.config import settings
from app.services.llm import get_chat_model


def extract_concepts(text: str) -> dict:
    # Provider-agnostic dispatcher (refactored 2026-07-09). Default: Gemini 2.5 Flash.
    llm = get_chat_model(temperature=0)

    prompt = (
        "Extract key concepts (nodes) and their relationships (edges) from the following text.\n"
        "Return a JSON object with this exact structure:\n"
        "{\n"
        "  \"nodes\": [\n"
        "    {\"title\": \"Concept Name\", \"description\": \"Brief description\", \"keywords\": [\"keyword1\", \"keyword2\"], \"aliases\": [\"alias1\"], \"confidence\": 0.9}\n"
        "  ],\n"
        "  \"edges\": [\n"
        "    {\"source\": \"Concept A\", \"target\": \"Concept B\", \"type\": \"Relationship Type\", \"confidence\": 0.8}\n"
        "  ]\n"
        "}\n"
        "Ensure the output is valid JSON and nothing else.\n"
        f"Text:\n{text}"
    )

    for attempt in range(3):
        try:
            res = llm.invoke(prompt)
            content = res.content.strip()

            # Clean markdown code blocks if the model returned them
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n", "", content)
                content = re.sub(r"\n```$", "", content)
                content = content.strip()

            data = json.loads(content)
            if "nodes" in data and "edges" in data:
                return data
        except Exception:
            continue

    return {"nodes": [], "edges": []}
