You are writing a technical deep-dive summary of a knowledge-graph node for a domain expert.

NODE:
- Name: {{node_name}}
- Type: {{node_type}}
- Properties: {{node_properties}}

NEIGHBORS (1-hop):
{{neighbors_text}}

Cover: structural role in the graph (why it exists as a node vs. just an edge attribute), key relationships and their semantics, edge cases or failure modes implied by the neighborhood, and any invariants worth preserving when this node is mutated. Use precise terminology. Mention specific neighbor relationships by name. Aim for ~400 words, max 500.