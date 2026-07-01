import requests
import os
from app.core.config import settings

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

def traverse_project_graph(project_id: str, jwt_token: str, start_node_id: str, depth: int = 3) -> dict:
    """Traverses the graph starting from a specific node."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/traverse/{start_node_id}?depth={depth}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed to traverse graph. Status: {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": f"Exception occurred while traversing graph: {str(e)}"}
