"""Hybrid search combining semantic search on document chunks and graph nodes.

Extracted from graph_tools.py. Reuses GraphClient and EmbeddingService.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from app.clients.graph_client import GraphClient, extract_node_id
from app.clients.nestjs_client import NestJSClient
from app.core.config import settings
from app.repositories.vector_store import search as vector_search
from app.services.embedding_service import EmbeddingService, embedding_service

# Defaults
_default_nestjs = NestJSClient(settings.NESTJS_API_URL)
_default_graph = GraphClient(_default_nestjs)


def _rank_candidate_nodes(chunks: list, nodes: list, query: str, k: int) -> list:
    """Rank nodes using lightweight heuristic (no embedding API calls in loop).

    Scoring:
    - Keyword match: query tokens found in node label/properties
    - Chunk reference boost: chunk metadata references this node
    """
    query_tokens = set(query.lower().split())
    chunk_node_refs = set()

    for chunk in chunks:
        if isinstance(chunk, dict):
            metadata = chunk.get("metadata", {})
            if isinstance(metadata, dict) and "nodeId" in metadata:
                chunk_node_refs.add(metadata["nodeId"])
            chunk_content = chunk.get("content", "").lower()
            for node in nodes:
                node_label = node.get("label") or node.get("name") or ""
                node_label = node_label.lower() if isinstance(node_label, str) else ""
                if node_label and len(node_label) > 3 and node_label in chunk_content:
                    chunk_node_refs.add(extract_node_id(node))

    ranked: list[Tuple[dict, float]] = []
    for node in nodes:
        score = 0.0
        node_id = extract_node_id(node)
        node_label = node.get("label") or node.get("name") or ""
        node_label = node_label.lower() if isinstance(node_label, str) else ""

        # Keyword match in label
        node_tokens = set(node_label.split())
        keyword_overlap = len(query_tokens & node_tokens)
        score += keyword_overlap * 2.0

        # Keyword match in properties
        properties = node.get("properties", {})
        if isinstance(properties, dict):
            prop_text = " ".join(str(v).lower() for v in properties.values() if v)
            prop_tokens = set(prop_text.split())
            score += len(query_tokens & prop_tokens)

        # Chunk reference boost
        if node_id in chunk_node_refs:
            score += 5.0

        if score > 0 or len(ranked) < k:
            ranked.append((node, score))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:k]


def search_by_embedding(
    project_id: str,
    query: str,
    k: int = 5,
    *,
    embedding_svc: EmbeddingService = None,
) -> list:
    """Search document chunks using semantic similarity (pgvector)."""
    try:
        svc = embedding_svc or embedding_service
        query_embedding = svc.get_embedding(query)
        return vector_search(project_id, query_embedding, k=k)
    except Exception as e:
        return [{"error": f"Exception in semantic search: {str(e)}"}]


def _run_async(coro):
    """Run async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def hybrid_search(
    project_id: str,
    query: str,
    jwt_token: str,
    k: int | None = None,
    *,
    graph_client: GraphClient = None,
    embedding_service: EmbeddingService = None,
) -> dict:
    """Hybrid search combining semantic search on chunks and graph nodes.

    Steps:
    1. Retrieve top-k document chunks by embedding similarity
    2. Retrieve all nodes, rank via lightweight keyword + chunk heuristic
    3. Take top HYBRID_TOP_K nodes
    4. Traverse HYBRID_TRAVERSE_DEPTH hops from each top node
    5. Deduplicate and limit to HYBRID_MAX_NODES
    """
    gc = graph_client or _default_graph
    es = embedding_service or embedding_service

    try:
        top_k = k if k is not None else settings.HYBRID_TOP_K
        traverse_depth = settings.HYBRID_TRAVERSE_DEPTH
        max_nodes = settings.HYBRID_MAX_NODES

        # Step 1: Chunks via semantic search
        chunks = search_by_embedding(project_id, query, k=top_k, embedding_svc=es)

        # Step 2: All nodes via GraphClient
        nodes_response = _run_async(gc.get_nodes(project_id, jwt_token))
        if isinstance(nodes_response, dict) and "error" in nodes_response:
            return {"chunks": chunks, "nodes": [], "error": nodes_response["error"]}

        all_nodes = nodes_response if isinstance(nodes_response, list) else nodes_response.get("data", [])
        top_nodes = _rank_candidate_nodes(chunks, all_nodes, query, top_k)

        # Step 3: Traverse from each top node
        discovered_nodes: Dict[str, dict] = {}
        for node, score in top_nodes:
            node_id = extract_node_id(node)
            if node_id and node_id not in discovered_nodes:
                discovered_nodes[node_id] = {**node, "similarity_score": score}

            traversal_result = _run_async(
                gc.traverse_graph(project_id, jwt_token, node_id, depth=traverse_depth)
            )

            if isinstance(traversal_result, dict) and "error" not in traversal_result:
                traversed_nodes = (
                    traversal_result
                    if isinstance(traversal_result, list)
                    else (traversal_result.get("nodes") or traversal_result.get("data") or [])
                )
                for tnode in traversed_nodes:
                    tid = extract_node_id(tnode)
                    if tid and tid not in discovered_nodes:
                        discovered_nodes[tid] = tnode

        # Step 4: Limit to max_nodes
        final_nodes = list(discovered_nodes.values())[:max_nodes]
        return {"chunks": chunks, "nodes": final_nodes}

    except Exception as e:
        return {"error": f"Exception in hybrid search: {str(e)}", "chunks": [], "nodes": []}
