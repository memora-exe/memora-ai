# Inputs
- Combined document text (may be truncated to fit within budget): {{combined_text}}
- Maximum number of concepts to extract: {{max_concepts}}

# Task
You are reading one or more documents and extracting the topic plus 5–15
concept noun phrases suitable for vector retrieval. Prefer canonical,
domain-specific concept names (e.g. "Linear Regression", "Transformer
architecture") over generic words (e.g. "data", "model"). A concept should be
short (1–3 words), capitalized/named, and useful as a search query.

Return strictly a JSON object: {"topic": string, "concepts": string[]}.
If nothing meaningful is found, return {"topic": "", "concepts": []}.
