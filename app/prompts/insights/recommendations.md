### Structural Recommendations

Repository overview:
- Nodes: {{node_count}}
- Edges: {{edge_count}}
- Fragmentation ratio: {{fragmentation_ratio}}

High-centrality hubs (good connectors):
{{important_nodes}}

Low-degree / isolated nodes (knowledge gaps):
{{gaps_list}}

Topic type coverage (count per nodeTypeId):
{{topic_coverage}}

Based on the metrics above, produce a concise Markdown report titled
"### Structural Recommendations" with 4-7 numbered action items. For each item,
name the specific node, type, or pattern the user should investigate (linking
gaps to their closest hub, adding edges to break isolated components, balancing
over- vs under-represented topic types, etc.). Use only the data above; do not
invent new metrics. Reply with Markdown only.