from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json


def extract_concepts(text: str) -> dict:
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

    for _ in range(3):
        try:
            res = llm.invoke(prompt)
            data = parse_llm_json(res, fallback={})
            if "nodes" in data and "edges" in data:
                return data
        except Exception:
            continue

    return {"nodes": [], "edges": []}
