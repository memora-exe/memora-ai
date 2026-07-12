import requests
import os
from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.services.vector_store import search as vector_search

NESTJS_API_URL = settings.NESTJS_API_URL

def get_project_nodes(project_id: str, jwt_token: str) -> dict:
    """Queries all nodes in a specific project."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/nodes"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to fetch nodes. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception occurred while fetching nodes: {str(e)}"}

def get_project_edges(project_id: str, jwt_token: str) -> dict:
    """Queries all edges in a specific project."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/edges"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to fetch edges. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception occurred while fetching edges: {str(e)}"}

def query_project_graph(project_id: str, jwt_token: str, query_params: dict) -> dict:
    """Queries the project graph with optional filters like nodeTypeIds, edgeTypeIds."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/query"
    try:
        response = requests.post(url, headers=headers, json=query_params)
        if response.status_code == 201 or response.status_code == 200:
            return response.json()
        return {"error": f"Failed to query graph. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception occurred while querying graph: {str(e)}"}

def create_project_node(project_id: str, jwt_token: str, payload: dict) -> dict:
    """POST a new node to the project graph. Returns the created node or error."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/nodes"
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Failed to create node. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception creating node: {str(e)}"}


def update_project_node(project_id: str, jwt_token: str, payload: dict) -> dict:
    """PATCH an existing node in the project graph. Returns the updated node or error."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/nodes"
    try:
        response = requests.patch(url, headers=headers, json=payload)
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Failed to update node. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception updating node: {str(e)}"}


def delete_project_node(project_id: str, jwt_token: str, node_id: str) -> dict:
    """DELETE a node by ID from the project graph. Returns success or error."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/nodes/{node_id}"
    try:
        response = requests.delete(url, headers=headers)
        if response.status_code in (200, 204):
            return {"success": True, "nodeId": node_id}
        return {"error": f"Failed to delete node. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception deleting node: {str(e)}"}


def create_project_edge(project_id: str, jwt_token: str, payload: dict) -> dict:
    """POST /projects/:pid/graph/edges — create edge."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/edges"
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Failed to create edge. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception creating edge: {str(e)}"}


def update_project_edge(project_id: str, jwt_token: str, payload: dict) -> dict:
    """PATCH /projects/:pid/graph/edges — update edge."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/edges"
    try:
        response = requests.patch(url, headers=headers, json=payload)
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Failed to update edge. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception updating edge: {str(e)}"}


def delete_project_edge(project_id: str, jwt_token: str, edge_id: str) -> dict:
    """DELETE /projects/:pid/graph/edges/:edgeId."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/edges/{edge_id}"
    try:
        response = requests.delete(url, headers=headers)
        if response.status_code in (200, 204):
            return {"success": True, "edgeId": edge_id}
        return {"error": f"Failed to delete edge. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception deleting edge: {str(e)}"}


def list_project_node_types(project_id: str, jwt_token: str) -> dict:
    """GET /projects/:pid/graph/node-types."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/node-types"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to list node types. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception listing node types: {str(e)}"}


def list_project_files(project_id: str, jwt_token: str) -> dict:
    """List all files uploaded to the current project."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/files/project/{project_id}"
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to list files. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception listing files: {str(e)}"}


def read_file_content(project_id: str, file_id: str, jwt_token: str) -> dict:
    """Read parsed text content of a single uploaded file."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/files/{file_id}/content"
    try:
        response = requests.get(url, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to read file. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception reading file: {str(e)}"}


def traverse_project_graph(project_id: str, jwt_token: str, start_node_id: str, depth: int = 3) -> dict:
    """Traverses the graph starting from a specific node."""
    # ponytail: defensive guard against LLM hallucinating "None" / "null" / empty ids — earlier
    # the AI passed Python's repr(None)="None" into the URL and BE logs spammed with /traverse/None.
    if start_node_id is None or str(start_node_id).strip() in ("", "None", "null"):
        return {"error": "missing start_node_id", "nodes": [], "edges": []}
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/traverse/{start_node_id}?depth={depth}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to traverse graph. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception occurred while traversing graph: {str(e)}"}

def llm_search_by_embedding(project_id: str, query: str, k: int = 5) -> list:
    """Search document chunks using semantic similarity (pgvector) in a project."""
    try:
        query_embedding = embedding_service.get_embedding(query)
        return vector_search(project_id, query_embedding, k=k)
    except Exception as e:
        return [{"error": f"Exception in semantic search: {str(e)}"}]


def _rank_candidate_nodes(chunks: list, nodes: list, query: str, k: int) -> list:
    """
    Rank nodes using a lightweight heuristic (no embedding API calls in loop).

    Scoring:
    - Keyword match: query tokens found in node label/properties
    - Chunk reference boost: chunk metadata references this node (by ID or fuzzy name match)

    Returns: list of (node, score) tuples, sorted desc, top k
    """
    query_tokens = set(query.lower().split())
    chunk_node_refs = set()

    # Extract node references from chunks (metadata nodeId or fuzzy name match)
    for chunk in chunks:
        if isinstance(chunk, dict):
            metadata = chunk.get('metadata', {})
            if isinstance(metadata, dict) and 'nodeId' in metadata:
                chunk_node_refs.add(metadata['nodeId'])
            # Fuzzy: check if chunk content mentions node names (simple substring)
            chunk_content = chunk.get('content', '').lower()
            for node in nodes:
                node_label = node.get('label') or node.get('name') or ''
                node_label = node_label.lower() if isinstance(node_label, str) else ''
                if node_label and len(node_label) > 3 and node_label in chunk_content:
                    chunk_node_refs.add(node.get('id') or node.get('nodeId') or node.get('elementId'))

    ranked = []
    for node in nodes:
        score = 0.0
        node_id = node.get('id') or node.get('nodeId') or node.get('elementId')
        node_label = node.get('label') or node.get('name') or ''
        node_label = node_label.lower() if isinstance(node_label, str) else ''

        # Keyword match in label
        node_tokens = set(node_label.split())
        keyword_overlap = len(query_tokens & node_tokens)
        score += keyword_overlap * 2.0

        # Keyword match in properties
        properties = node.get('properties', {})
        if isinstance(properties, dict):
            prop_text = ' '.join(str(v).lower() for v in properties.values() if v)
            prop_tokens = set(prop_text.split())
            score += len(query_tokens & prop_tokens)

        # Chunk reference boost
        if node_id in chunk_node_refs:
            score += 5.0

        if score > 0 or len(ranked) < k:
            ranked.append((node, score))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:k]

def llm_hybrid_search(project_id: str, query: str, jwt_token: str, k: int = None) -> dict:
    """
    Hybrid search combining semantic search on document chunks and graph nodes.

    Steps:
    1. Retrieve top-k document chunks by embedding similarity
    2. Retrieve all nodes, rank via lightweight keyword + chunk-reference heuristic
    3. Take top HYBRID_TOP_K nodes
    4. Traverse HYBRID_TRAVERSE_DEPTH hops from each top node
    5. Deduplicate and limit to HYBRID_MAX_NODES total nodes

    Returns:
        {
            "chunks": [...],  # Top-k chunks with scores
            "nodes": [...]    # Ranked and traversed nodes, limited to HYBRID_MAX_NODES
        }
    """
    try:
        from app.core.config import settings

        # Use config defaults if not provided
        top_k = k if k is not None else settings.HYBRID_TOP_K
        traverse_depth = settings.HYBRID_TRAVERSE_DEPTH
        max_nodes = settings.HYBRID_MAX_NODES

        # Step 1: Get top-k chunks via semantic search
        chunks = llm_search_by_embedding(project_id, query, k=top_k)

        # Step 2: Get all nodes and rank via lightweight keyword heuristic (no API calls in loop)
        nodes_response = get_project_nodes(project_id, jwt_token)

        if "error" in nodes_response:
            return {"chunks": chunks, "nodes": [], "error": nodes_response["error"]}

        all_nodes = nodes_response if isinstance(nodes_response, list) else nodes_response.get("data", [])

        # Rank nodes using keyword + chunk-reference heuristic
        top_nodes = _rank_candidate_nodes(chunks, all_nodes, query, top_k)

        # Step 3: Traverse from each top node
        discovered_nodes = {}
        for node, score in top_nodes:
            # ponytail: BE returns 'nodeId'; earlier code only read 'id' which is always None,
            # so traversed_nodes loop received Python's repr(None)="None" → /traverse/None 500s.
            node_id = node.get('nodeId') or node.get('id') or node.get('elementId')
            if node_id and node_id not in discovered_nodes:
                discovered_nodes[node_id] = {**node, "similarity_score": score}

            # Traverse from this node
            traversal_result = traverse_project_graph(project_id, jwt_token, node_id, depth=traverse_depth)

            if "error" not in traversal_result:
                traversed_nodes = traversal_result if isinstance(traversal_result, list) else (traversal_result.get("nodes") or traversal_result.get("data") or [])
                for tnode in traversed_nodes:
                    tid = tnode.get('nodeId') or tnode.get('id') or tnode.get('elementId')
                    if tid and tid not in discovered_nodes:
                        discovered_nodes[tid] = tnode

        # Step 4: Limit to max_nodes
        final_nodes = list(discovered_nodes.values())[:max_nodes]

        return {
            "chunks": chunks,
            "nodes": final_nodes
        }
    except Exception as e:
        return {"error": f"Exception in hybrid search: {str(e)}", "chunks": [], "nodes": []}

