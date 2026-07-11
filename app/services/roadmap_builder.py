"""Phase 4 — Learning Navigator (Roadmaps) builder.

Pipeline:
  1. (doc-aware) extract topic + concepts from already-ingested document chunks
  2. union seeds with user-supplied topic tokens
  3. pgvector top-K retrieval of chunks via the Phase 2 helper
  4. match chunk metadata → seed node ids
  5. fetch all project nodes/edges, Kahn topological sort
  6. partition sorted nodes into ≤ ROADMAP_MAX_STAGES
  7. per-stage: ask LLM to generate title + 2-3 sentence description
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque

from app.common.logger.logger import get_logger
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.services.document_topic_extractor import extract_topic_from_files
from app.services.graph_tools import (
    get_project_edges,
    get_project_nodes,
    llm_search_by_embedding,
)
from app.services.llm import get_chat_model

logger = get_logger("RoadmapBuilder")


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


def _match_seed_nodes(chunks: list, project_nodes: list) -> list[dict]:
    """Pick node objects whose id or label is referenced by any chunk."""
    by_id = {n.get("id"): n for n in project_nodes if n.get("id")}
    label_to_id: dict[str, str] = {}
    for n in project_nodes:
        label = (n.get("label") or n.get("name") or "").strip()
        if label:
            label_to_id[label.lower()] = n["id"]

    seed_ids: list[str] = []
    seen: set[str] = set()
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        metadata = chunk.get("metadata") or {}
        if isinstance(metadata, dict):
            nid = metadata.get("nodeId")
            if nid in by_id and nid not in seen:
                seen.add(nid)
                seed_ids.append(nid)
        content = (chunk.get("content") or "").lower()
        if not content:
            continue
        for label, nid in label_to_id.items():
            if len(label) > 3 and label in content and nid not in seen:
                seen.add(nid)
                seed_ids.append(nid)
    return [by_id[nid] for nid in seed_ids if nid in by_id]


def _kahn_topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Topological order over node ids using `sourceNodeId -> targetNodeId`.

    Falls back to insertion order when the graph is disconnected or has cycles
    (Prerequisite assumptions in Phase 4 are best-effort; we don't crash on
    non-DAGs — we just append the remainder unsorted)."""
    id_to_node = {n["id"]: n for n in nodes if n.get("id")}
    indeg: dict[str, int] = defaultdict(int)
    out_edges: dict[str, list[str]] = defaultdict(list)
    node_ids = list(id_to_node.keys())

    for e in edges or []:
        if not isinstance(e, dict):
            continue
        src = e.get("sourceNodeId") or e.get("source")
        dst = e.get("targetNodeId") or e.get("target")
        if src in id_to_node and dst in id_to_node and src != dst:
            out_edges[src].append(dst)
            indeg[dst] += 1

    # Roots: nodes with in-degree 0 first, then cycle/isolated tail.
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

    # Append any nodes not reached by the topological pass (cycle or isolated).
    for nid in node_ids:
        if nid not in in_sorted:
            sorted_ids.append(nid)
    return sorted_ids


def _partition_stages(ordered_node_ids: list[str], max_stages: int) -> list[list[str]]:
    """Evenly split ordered ids across up to `max_stages` buckets."""
    if not ordered_node_ids:
        return []
    stages = max(1, min(max_stages, len(ordered_node_ids)))
    bucket: list[list[str]] = [[] for _ in range(stages)]
    for i, nid in enumerate(ordered_node_ids):
        bucket[i * stages // len(ordered_node_ids)].append(nid)
    return [b for b in bucket if b]


async def _describe_stage(topic: str, stage_index: int, total_stages: int, concepts: list[str]) -> dict:
    """Ask the configured LLM for a title + 2-3 sentence description."""
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
        llm = get_chat_model(temperature=0.3, override_model=settings.ROADMAP_MODEL)
        raw = await llm.ainvoke(prompt)
        text = (raw.content if hasattr(raw, "content") else str(raw)).strip()
    except Exception as e:
        logger.warning(f"Stage-description LLM call failed: {e}")
        return {
            "title": f"Stage {stage_index}",
            "description": "Stage description could not be generated.",
        }

    match = re.search(r"\{[\s\S]*\}", text)
    payload = match.group(0) if match else text
    try:
        data = json.loads(payload)
        title = str(data.get("title") or f"Stage {stage_index}").strip()
        description = str(data.get("description") or "Stage description unavailable.").strip()
        if not title.startswith(f"Stage {stage_index}"):
            title = f"Stage {stage_index}: {title}"
        return {"title": title, "description": description}
    except json.JSONDecodeError:
        return {"title": f"Stage {stage_index}", "description": text[:300]}


async def build_roadmap(
    project_id: str,
    topic: str | None,
    file_ids: list[str],
    depth: int | None,
    jwt_token: str,
) -> dict:
    """Build a roadmap structure. Returns {topic, sourceFileIds, stages: [...]}."""
    if not topic and not file_ids:
        raise ValueError("At least one of `topic` or `fileIds` is required.")

    # 1. (doc-aware) extract topic + concepts from selected documents
    extracted: dict = {"topic": "", "concepts": []}
    if file_ids:
        extracted = await extract_topic_from_files(file_ids)

    # 2. union seeds; user-supplied topic wins as the headline
    headline_topic = (topic or extracted.get("topic") or "Learning Roadmap").strip()
    seed_concepts = _seed_concepts(topic or "", extracted.get("concepts", []))
    if not seed_concepts:
        seed_concepts = [headline_topic]

    # 3. pgvector top-K retrieval
    chunks = llm_search_by_embedding(project_id, " ".join(seed_concepts), k=settings.ROADMAP_TOP_K_SEEDS)
    if isinstance(chunks, dict) and "error" in chunks:
        chunks = []

    # 4. seed node ids from chunks
    nodes_resp = get_project_nodes(project_id, jwt_token)
    project_nodes = nodes_resp if isinstance(nodes_resp, list) else (nodes_resp.get("data", []) if isinstance(nodes_resp, dict) else [])
    if not isinstance(project_nodes, list):
        project_nodes = []
    seed_nodes = _match_seed_nodes(chunks, project_nodes)

    # 5. run topological sort over ALL project nodes, then move seeds to the front
    edges_resp = get_project_edges(project_id, jwt_token)
    project_edges = edges_resp if isinstance(edges_resp, list) else (edges_resp.get("data", []) if isinstance(edges_resp, dict) else [])
    if not isinstance(project_edges, list):
        project_edges = []
    ordered_ids = _kahn_topological_sort(project_nodes, project_edges)
    seed_id_set = {n["id"] for n in seed_nodes}
    seed_ids_ordered = [nid for nid in ordered_ids if nid in seed_id_set]
    other_ids = [nid for nid in ordered_ids if nid not in seed_id_set]
    final_order = seed_ids_ordered + other_ids

    # 6. partition — `depth` caps the number of stages
    capped_stages = max(1, min(settings.ROADMAP_MAX_STAGES, depth or settings.ROADMAP_MAX_STAGES))
    buckets = _partition_stages(final_order, capped_stages)
    if not buckets:
        buckets = [[]]

    # 7. per-stage description
    stages: list[dict] = []
    for idx, bucket in enumerate(buckets, start=1):
        bucket_nodes = [n for n in project_nodes if n.get("id") in set(bucket)]
        concepts = [
            (n.get("label") or n.get("name") or n.get("id") or "")
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
