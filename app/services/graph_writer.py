import requests
from app.core.config import settings

NESTJS_API_URL = settings.NESTJS_API_URL

def create_node(project_id: str, jwt_token: str, name: str, data: dict = None) -> str:
    """Creates a node via the NestJS API and returns its nodeId."""
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/nodes"
    payload = {
        "nodeName": name,
        "data": data or {}
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            res_data = response.json()
            return res_data.get("nodeId")
        else:
            raise Exception(f"Failed to create node. Status: {response.status_code}, Detail: {response.text}")
    except Exception as e:
        raise Exception(f"Error creating node '{name}': {str(e)}")

def create_edge(project_id: str, jwt_token: str, source_node_id: str, target_node_id: str, properties: dict = None) -> str:
    """Creates an edge via the NestJS API."""
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    url = f"{NESTJS_API_URL}/projects/{project_id}/graph/edges"
    payload = {
        "sourceNodeId": source_node_id,
        "targetNodeId": target_node_id,
        "properties": properties or {}
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            res_data = response.json()
            return res_data.get("edgeId")
        else:
            raise Exception(f"Failed to create edge. Status: {response.status_code}, Detail: {response.text}")
    except Exception as e:
        raise Exception(f"Error creating edge: {str(e)}")

def write_graph(project_id: str, jwt_token: str, graph_data: dict):
    """Writes nodes and edges to the graph database via NestJS API."""
    node_map = {}

    # Write nodes
    for node in graph_data.get("nodes", []):
        name = node.get("title")
        if not name:
            continue
        node_properties = {
            "description": node.get("description", ""),
            "keywords": node.get("keywords", []),
            "aliases": node.get("aliases", []),
            "confidence": node.get("confidence", 1.0)
        }
        try:
            node_id = create_node(project_id, jwt_token, name, node_properties)
            node_map[name.lower()] = node_id
        except Exception as e:
            # Log error and continue to not break the whole pipeline
            print(f"Error in write_graph node creation: {str(e)}")

    # Write edges
    for edge in graph_data.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue

        source_id = node_map.get(source.lower())
        target_id = node_map.get(target.lower())

        if not source_id or not target_id:
            print(f"Skipping edge creation: source '{source}' or target '{target}' node not found.")
            continue

        edge_properties = {
            "type": edge.get("type", "RELATED_TO"),
            "confidence": edge.get("confidence", 1.0)
        }
        try:
            create_edge(project_id, jwt_token, source_id, target_id, edge_properties)
        except Exception as e:
            print(f"Error in write_graph edge creation: {str(e)}")
