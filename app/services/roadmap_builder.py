"""Phase 4 — Learning Navigator (Roadmaps) builder.

Pipeline:
  1. (doc-aware) extract topic + concepts from locally stored documents
  2. union seeds with user-supplied topic tokens
  3. match seed labels directly against graph nodes
  4. fetch all project nodes/edges, Kahn topological sort
  5. partition sorted nodes into <= ROADMAP_MAX_STAGES
  6. per-stage: ask LLM to generate title + 2-3 sentence description
"""
from __future__ import annotations

import re
from collections import defaultdict, deque

from app.clients.graph_client import GraphClient, extract_edge_endpoints, extract_node_id
from app.clients.nestjs_client import NestJSClient
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.services.document_topic_extractor import extract_topic_from_files
from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json

logger = get_logger("RoadmapBuilder")

_default_graph = GraphClient(NestJSClient(settings.NESTJS_API_URL))


def _seed_concepts(topic: str, extracted_concepts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in ([topic] if topic else []):
        for tok in re.split(r"[\s,]+", raw.strip()):
            tok = tok.strip()
            if tok and tok.lower() not in seen:
                seen.add(tok.lower())
                out.append(tok)
    for concept in extracted_concepts:
        c = concept.strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def _kahn_topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Topological order over node ids using sourceNodeId -> targetNodeId."""
    id_to_node = {extract_node_id(n): n for n in nodes if extract_node_id(n)}
    indeg: dict[str, int] = defaultdict(int)
    out_edges: dict[str, list[str]] = defaultdict(list)
    node_ids = list(id_to_node.keys())

    for e in edges or []:
        if not isinstance(e, dict):
            continue
        src, dst = extract_edge_endpoints(e)
        if src in id_to_node and dst in id_to_node and src != dst:
            out_edges[src].append(dst)
            indeg[dst] += 1

    queue = deque([nid for nid in node_ids if indeg[nid] == 0])
    sorted_ids: list[str] = []
    in_sorted: set[str] = set()
    while queue:
        nid = queue.popleft()
        if nid in in_sorted:
            continue
        in_sorted.add(nid)
        sorted_ids.append(nid)
        for child in out_edges.get(nid, []):
            indeg[child] -= 1
            if indeg[child] == 0 and child not in in_sorted:
                queue.append(child)

    for nid in node_ids:
        if nid not in in_sorted:
            sorted_ids.append(nid)
    return sorted_ids


def _partition_stages(ordered_node_ids: list[str], max_stages: int) -> list[list[str]]:
    if not ordered_node_ids:
        return []
    stages = max(1, min(max_stages, len(ordered_node_ids)))
    bucket: list[list[str]] = [[] for _ in range(stages)]
    for i, nid in enumerate(ordered_node_ids):
        bucket[i * stages // len(ordered_node_ids)].append(nid)
    return [b for b in bucket if b]


async def _describe_stage(topic: str, stage_index: int, total_stages: int, concepts: list[str]) -> dict:
    concepts_list = ", ".join(concepts[:12]) if concepts else "(no specific concept labels)"
    prompt = render_prompt(
        "roadmap_stage_description.md",
        {
            "topic": topic or "Untitled Learning Roadmap",
            "stage_index": str(stage_index),
            "total_stages": str(total_stages),
            "concepts_list": concepts_list,
        },
    )
    try:
        llm = get_chat_model(temperature=0.3)
        raw = await llm.ainvoke(prompt)
    except Exception as e:
        logger.warning(f"Stage-description LLM call failed: {e}")
        return {
            "title": f"Stage {stage_index}",
            "description": "Stage description could not be generated.",
        }

    data = parse_llm_json(raw, fallback={})
    title = str(data.get("title") or f"Stage {stage_index}").strip()
    description = str(data.get("description") or "Stage description unavailable.").strip()
    if not title.startswith(f"Stage {stage_index}"):
        title = f"Stage {stage_index}: {title}"
    return {"title": title, "description": description}


async def build_roadmap(
    project_id: str,
    topic: str | None,
    file_ids: list[str],
    depth: int | None,
    jwt_token: str,
    *,
    graph_client: GraphClient = None,
) -> dict:
    """Build a roadmap structure. Returns {topic, sourceFileIds, stages: [...]}."""
    if not topic and not file_ids:
        raise ValueError("At least one of `topic` or `fileIds` is required.")

    gc = graph_client or _default_graph

    extracted: dict = {"topic": "", "concepts": []}
    if file_ids:
        extracted = await extract_topic_from_files(file_ids, project_id)

    headline_topic = (topic or extracted.get("topic") or "Learning Roadmap").strip()
    seed_concepts = _seed_concepts(topic or "", extracted.get("concepts", []))
    if not seed_concepts:
        seed_concepts = [headline_topic]

    nodes_resp = await gc.get_nodes(project_id, jwt_token)
    project_nodes = nodes_resp if isinstance(nodes_resp, list) else (nodes_resp.get("data", []) if isinstance(nodes_resp, dict) else [])
    if not isinstance(project_nodes, list):
        project_nodes = []
    seed_nodes = [
        node for node in project_nodes
        if any(seed.lower() in (node.get("label") or node.get("name") or "").lower() for seed in seed_concepts)
    ]

    edges_resp = await gc.get_edges(project_id, jwt_token)
    project_edges = edges_resp if isinstance(edges_resp, list) else (edges_resp.get("data", []) if isinstance(edges_resp, dict) else [])
    if not isinstance(project_edges, list):
        project_edges = []
    ordered_ids = _kahn_topological_sort(project_nodes, project_edges)
    seed_id_set = {extract_node_id(n) for n in seed_nodes}
    seed_ids_ordered = [nid for nid in ordered_ids if nid in seed_id_set]
    other_ids = [nid for nid in ordered_ids if nid not in seed_id_set]
    final_order = seed_ids_ordered + other_ids

    capped_stages = max(1, min(settings.ROADMAP_MAX_STAGES, depth or settings.ROADMAP_MAX_STAGES))
    buckets = _partition_stages(final_order, capped_stages)
    if not buckets:
        buckets = [[]]

    stages: list[dict] = []
    for idx, bucket in enumerate(buckets, start=1):
        bucket_nodes = [n for n in project_nodes if extract_node_id(n) in set(bucket)]
        concepts = [
            (n.get("label") or n.get("name") or extract_node_id(n) or "")
            for n in bucket_nodes
        ]
        meta = await _describe_stage(headline_topic, idx, len(buckets), concepts)
        stages.append({
            "stage": idx,
            "title": meta["title"],
            "nodeIds": bucket,
            "description": meta["description"],
        })

    return {
        "topic": headline_topic,
        "sourceFileIds": list(file_ids or []),
        "stages": stages,
    }
