# Inputs
- Topic: {{topic}}
- Stage index (1-based): {{stage_index}} of {{total_stages}}
- Concepts in this stage: {{concepts_list}}

# Task
Generate a short learning stage title and a 2-3 sentence description for the
given stage of the topic, using only the provided concepts. The title MUST
follow the format "Stage {{stage_index}}: <title>" (in Vietnamese when the
topic itself is Vietnamese, otherwise English).

Return strictly a JSON object: {"title": "...", "description": "..."}.
