from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json


from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json


def extract_concepts(text: str) -> dict:
    llm = get_chat_model(temperature=0.1)

    prompt = (
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
        "  \"nodes\": [\n"
        "    {\"title\": \"Concept Name\", \"description\": \"Rigorous technical description\", \"keywords\": [\"keyword1\", \"keyword2\"], \"aliases\": [\"alias1\"], \"confidence\": 0.95}\n"
        "  ],\n"
        "  \"edges\": [\n"
        "    {\"source\": \"Concept A\", \"target\": \"Concept B\", \"type\": \"PREREQUISITE\", \"confidence\": 0.9}\n"
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
