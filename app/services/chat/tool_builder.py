"""LLM tool closures for the chat agent — extracted from agent_service.py.

Each closure captures (project_id, jwt_token, session_id) and delegates to
GraphClient (async) or local file storage. The ADK Agent calls these as
function tools — the docstrings ARE the tool descriptions the LLM sees.

Note: google-adk FunctionTool can call sync functions. For async graph_client
calls, we use asyncio.get_event_loop().run_until_complete() via a helper since
ADK runs tools synchronously within the agent loop. However, since ADK >=2.3
supports async tool functions, we mark them as regular functions and let ADK
handle the sync/async bridge.
"""
from __future__ import annotations

from app.clients.graph_client import GraphClient, extract_node_id
from app.services.chat.metadata_tracker import (
    record_highlight,
    record_mutation,
    record_path_highlight,
    set_metadata,
)
from app.services.document_processor import clean_extracted_text
from app.services.file_storage import grep_documents, list_documents, read_document


def build_graph_tools(
    project_id: str,
    jwt_token: str,
    session_id: str,
    *,
    graph_client: GraphClient,
) -> list:
    """Build the list of LLM-callable tools with injected context.

    Returns a list of plain functions whose docstrings serve as tool
    descriptions for the ADK Agent.
    """

    # -- helpers captured by closures --------------------------------------

    def _mut(action: str, *, nodes=(), edges=()):
        record_mutation(project_id, session_id, action, nodes=nodes, edges=edges)

    # ponytail: ADK tools are called synchronously inside the agent runner.
    # graph_client is async. We use a small bridge to run async in the
    # existing event loop. ADK >=2.3 supports async tools natively — when
    # upgrading, just make these `async def` and drop the bridge.
    import asyncio

    def _run(coro):
        """Run an async coroutine from a sync ADK tool context."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # We're inside an event loop (ADK runner). Use a new thread to
            # avoid blocking. This is the standard pattern for calling async
            # from sync in an already-running loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    # -- read tools --------------------------------------------------------

    def llm_get_all_nodes() -> dict:
        """Retrieve all knowledge graph nodes in the current project.
        Use this tool when the user asks about existing nodes, concepts, or entities in the project.

        Returns:
            dict: A list of all nodes with their properties (id, name, type, metadata, etc.).
        """
        return _run(graph_client.get_nodes(project_id, jwt_token))

    def llm_get_all_edges() -> dict:
        """Retrieve all edges (relationships) between nodes in the current project.
        Use this tool when the user asks about connections, relationships, or links between entities.

        Returns:
            dict: A list of all edges with their properties (id, sourceNodeId, targetNodeId, type, etc.).
        """
        return _run(graph_client.get_edges(project_id, jwt_token))

    def llm_query_graph(node_type_ids: list = None, edge_type_ids: list = None) -> dict:
        """Query specific parts of the project graph using optional filters on node types or edge types.
        Note: The UI no longer requires nodeType or edgeType, and wikilink mention edges have edgeTypeId=null.
        Prefer querying without filters or using llm_traverse_graph / llm_get_all_nodes.

        Args:
            node_type_ids (list): Optional legacy list of node type IDs to filter nodes by type.
            edge_type_ids (list): Optional legacy list of edge type IDs to filter edges by type.

        Returns:
            dict: Filtered graph result containing matched nodes and edges.
        """
        query_params = {}
        if node_type_ids:
            query_params["nodeTypeIds"] = node_type_ids
        if edge_type_ids:
            query_params["edgeTypeIds"] = edge_type_ids
        return _run(graph_client.query_graph(project_id, jwt_token, query_params))

    def llm_traverse_graph(start_node_id: str, depth: int = 3) -> dict:
        """Traverse the knowledge graph starting from a specific node up to a given depth.
        Use this when the user wants to explore what is connected to a specific node.

        Args:
            start_node_id (str): The ID of the starting node.
            depth (int): Maximum traversal depth. Default is 3.

        Returns:
            dict: Subgraph containing all reachable nodes and edges within the specified depth.
        """
        return _run(graph_client.traverse_graph(project_id, jwt_token, start_node_id, depth))

    def llm_glob_files(pattern: str = "*") -> list:
        """List parsed markdown documents available in this project."""
        return list_documents(project_id, pattern)

    def llm_grep_search(query: str, path_pattern: str = "*.md", case_sensitive: bool = False) -> list:
        """Search parsed document text, returning matching lines and context."""
        result = grep_documents(project_id, query, path_pattern, case_sensitive)
        set_metadata(project_id, session_id, {"fileMatches": result})
        return result

    def llm_read_file_content(file_id: str, offset: int = 1, limit: int = 100) -> dict:
        """Read a line range from a parsed markdown document."""
        res = read_document(project_id, file_id, offset, limit)
        if isinstance(res, dict) and "content" in res:
            res["content"] = clean_extracted_text(str(res["content"]))
        return res



    # -- write tools -------------------------------------------------------

    def llm_create_node(
        node_name: str,
        node_type_id: str = None,
        node_id: str = None,
        note: str = None,
        data: str = None,
    ) -> dict:
        """Create a new knowledge graph node in current project.

        Use when the user asks to capture a new concept, entity, person, or topic
        in the project. Populate `note` with the substantive text (an excerpt,
        summary, or analysis) and `data` with structured JSON metadata such as
        {"source": fileId} when the node was derived from a file.

        Args:
            node_name: display name for the new node (REQUIRED).
            node_type_id: existing node type id (UUID) to assign — omitted = no type.
            node_id: optional client-provided UUID; server assigns one when omitted.
            note: substantive text content for the node's note field (REQUIRED
                when the user shared a file or asked for the node to contain
                information; never leave empty in those cases).
            data: optional JSON string payload (e.g. '{"source": "<fileId>"}').

        Returns: created node with server-assigned id and properties.
        """
        payload = {"nodeName": node_name}
        if node_type_id:
            payload["nodeTypeId"] = node_type_id
        if node_id:
            payload["nodeId"] = node_id
        if note:
            payload["note"] = note
        if data:
            if isinstance(data, str):
                import json
                try:
                    payload["data"] = json.loads(data)
                except Exception:
                    payload["data"] = {"raw": data}
            else:
                payload["data"] = data
        result = _run(graph_client.create_node(project_id, jwt_token, payload))
        nid = None
        if isinstance(result, dict):
            nid = result.get("nodeId") or result.get("id")
        if nid:
            _mut("created", nodes=[nid])
        return result

    def llm_update_node(
        node_id: str,
        node_name: str = None,
        node_type_id: str = None,
        note: str = None,
        data: str = None,
    ) -> dict:
        """Update an existing knowledge graph node in current project.

        Omit any field to keep its current value. Pass `note` to overwrite the
        text content; pass `data` (JSON string) to overwrite the structured payload.
        """
        payload = {"nodeId": node_id}
        if node_name is not None:
            payload["nodeName"] = node_name
        if node_type_id is not None:
            payload["nodeTypeId"] = node_type_id
        if note is not None:
            payload["note"] = note
        if data is not None:
            if isinstance(data, str):
                import json
                try:
                    payload["data"] = json.loads(data)
                except Exception:
                    payload["data"] = {"raw": data}
            else:
                payload["data"] = data
        result = _run(graph_client.update_node(project_id, jwt_token, payload))
        if isinstance(result, dict):
            _mut("updated", nodes=[node_id])
        return result

    def llm_update_node_note(node_id: str, note: str) -> dict:
        """Convenience wrapper to set only the `note` field of an existing node.

        Use when the user asks to attach text to an existing concept (e.g. "ghi
        chú cho node X là: ...").
        """
        return llm_update_node(node_id=node_id, note=note)

    def llm_delete_node(node_id: str) -> dict:
        """Delete a knowledge graph node from the current project.
        Use this when the user explicitly asks to remove a node.
        This action is irreversible and will also remove all edges connected to the node.

        Args:
            node_id (str): The ID of the node to delete.

        Returns:
            dict: Confirmation with the deleted node's ID on success, or error details.
        """
        result = _run(graph_client.delete_node(project_id, jwt_token, node_id))
        if isinstance(result, dict) and not result.get("error"):
            _mut("deleted", nodes=[node_id])
        return result

    def llm_create_edge(
        source_node_id: str,
        target_node_id: str,
        edge_type_id: str = None,
        edge_properties: str = None,
        edge_id: str = None,
    ) -> dict:
        """Create a relationship between two existing nodes in the project.

        Use when the user describes a relation between two concepts they already
        know (or that you just created). Source and target must be nodeIds of
        nodes that already exist in this project; use llm_grep_search first if
        you are unsure.

        Args:
            source_node_id: id of the source node (REQUIRED).
            target_node_id: id of the target node (REQUIRED).
            edge_type_id: optional edge type id (UUID).
            edge_properties: optional JSON string or metadata text for the edge.
            edge_id: optional client-provided UUID; server assigns one if omitted.
        """
        payload = {"sourceNodeId": source_node_id, "targetNodeId": target_node_id}
        if edge_type_id:
            payload["edgeTypeId"] = edge_type_id
        if edge_properties:
            if isinstance(edge_properties, str):
                import json
                try:
                    payload["properties"] = json.loads(edge_properties)
                except Exception:
                    payload["properties"] = {"raw": edge_properties}
            else:
                payload["properties"] = edge_properties
        if edge_id:
            payload["edgeId"] = edge_id
        result = _run(graph_client.create_edge(project_id, jwt_token, payload))
        eid = None
        if isinstance(result, dict):
            eid = result.get("edgeId") or result.get("id")
        if eid:
            _mut("created", edges=[eid])
        return result

    def llm_update_edge(
        edge_id: str,
        source_node_id: str = None,
        target_node_id: str = None,
        edge_type_id: str = None,
        edge_properties: str = None,
    ) -> dict:
        """Update an existing edge. Omit any field to keep its current value."""
        payload = {"edgeId": edge_id}
        if source_node_id is not None:
            payload["sourceNodeId"] = source_node_id
        if target_node_id is not None:
            payload["targetNodeId"] = target_node_id
        if edge_type_id is not None:
            payload["edgeTypeId"] = edge_type_id
        if edge_properties is not None:
            if isinstance(edge_properties, str):
                import json
                try:
                    payload["properties"] = json.loads(edge_properties)
                except Exception:
                    payload["properties"] = {"raw": edge_properties}
            else:
                payload["properties"] = edge_properties
        result = _run(graph_client.update_edge(project_id, jwt_token, payload))
        if isinstance(result, dict):
            _mut("updated", edges=[edge_id])
        return result

    def llm_delete_edge(edge_id: str) -> dict:
        """Delete an edge by id."""
        result = _run(graph_client.delete_edge(project_id, jwt_token, edge_id))
        if isinstance(result, dict) and not result.get("error"):
            _mut("deleted", edges=[edge_id])
        return result

    # -- meta tools --------------------------------------------------------

    def llm_list_node_types() -> dict:
        """List all node types defined in the current project.

        Use when you need a nodeTypeId for llm_create_node / llm_update_node.
        Returns the array of node type entries: each has nodeTypeId, typeName,
        and optional schema. Pick the most specific existing type; do NOT invent
        a new id — if no type fits, omit nodeTypeId.
        """
        return _run(graph_client.get_node_types(project_id, jwt_token))

    def llm_list_files() -> dict:
        """List all files uploaded to the current project.
        Use this whenever the user mentions 'the file', 'document', 'report', 'PDF',
        or refers to a file without giving its name. Returns a dict with a list of
        {id, originalName, mimetype, size, ...} entries.
        """
        return _run(graph_client.list_files(project_id, jwt_token))

    def llm_read_file(file_id: str) -> dict:
        """Read parsed text content of a single uploaded file by its id.
        Use after llm_list_files to retrieve a specific file's content.
        """
        # First priority: clean parsed markdown from document storage
        doc = read_document(project_id, file_id, offset=1, limit=300)
        if doc and not doc.get("error") and doc.get("content"):
            content = clean_extracted_text(str(doc["content"]))
            if len(content) > 50000:
                content = content[:50000] + "\n\n[...truncated to 50KB for context safety...]"
            return {
                "fileId": file_id,
                "filename": doc.get("original_name", f"{file_id}.md"),
                "content": content,
                "total_lines": doc.get("total_lines", 0),
            }
        # Fallback to backend file content endpoint
        res = _run(graph_client.read_file_content(file_id, jwt_token))
        if isinstance(res, dict) and "content" in res:
            content = clean_extracted_text(str(res["content"]))
            if len(content) > 50000:
                content = content[:50000] + "\n\n[...truncated to 50KB for context safety...]"
            res["content"] = content
        return res

    def llm_highlight(
        items_json: str = None,
        default_color: str = "#00E676",
        description: str = "",
        nodes_or_edges: str = "nodes",
        ids: list = None,
    ) -> dict:
        """Highlight specific nodes on the graph with distinct, high-contrast colors.

        Args:
            items_json: JSON string representing a list of items to highlight:
                '[{"id": "node-uuid", "color": "#00E676", "name": "Node Label"}]'
                Colors must be vibrant 6-char hex (e.g. #00E676, #FF5722, #00E5FF, #FFD600, #FF1744).
            default_color: Hex color applied to items if items_json doesn't specify one.
            description: Short human-readable explanation of why these nodes are highlighted.
            nodes_or_edges: "nodes" (default) or "edges" (for backward compatibility).
            ids: Optional fallback list of IDs if items_json is not used.
        """
        import json
        import re

        def _clean_color(c: str) -> str:
            if not c or not isinstance(c, str):
                return default_color or "#00E676"
            c = c.strip()
            if not c.startswith("#"):
                c = f"#{c}"
            if re.match(r"^#[0-9a-fA-F]{6}$", c):
                return c.upper()
            return default_color or "#00E676"

        kind = (nodes_or_edges or "nodes").lower()
        items: list[dict] = []

        if items_json and isinstance(items_json, str):
            try:
                parsed = json.loads(items_json)
                if isinstance(parsed, list):
                    for entry in parsed:
                        if isinstance(entry, dict) and (entry.get("id") or entry.get("nodeId")):
                            nid = str(entry.get("id") or entry.get("nodeId"))
                            color = _clean_color(entry.get("color"))
                            name = entry.get("name") or entry.get("label") or nid
                            items.append({"id": nid, "color": color, "name": name, "kind": "node"})
                        elif isinstance(entry, str) and entry.strip():
                            nid = entry.strip()
                            items.append({"id": nid, "color": _clean_color(default_color), "name": nid, "kind": "node"})
            except Exception:
                pass

        if not items and ids:
            clean_ids = [str(i) for i in ids if i]
            for cid in clean_ids:
                items.append({
                    "id": cid,
                    "color": _clean_color(default_color),
                    "name": cid,
                    "kind": "edge" if kind == "edges" else "node",
                })

        if not items:
            return {"error": "no items or ids provided to highlight"}

        # Legacy mutation tracker support
        node_ids = [it["id"] for it in items if it.get("kind") == "node"]
        edge_ids = [it["id"] for it in items if it.get("kind") == "edge"]
        if node_ids:
            _mut("highlighted", nodes=node_ids)
        if edge_ids:
            _mut("highlighted", edges=edge_ids)

        record_highlight(project_id, session_id, items, description)
        return {
            "highlighted_count": len(items),
            "description": description,
            "items": items,
        }

    def llm_find_path(source_node: str, target_node: str) -> dict:
        """Find the shortest path and bridge concepts connecting two knowledge nodes.

        Use this tool when the user asks how two concepts are connected, what links
        concept A to concept B, or wants to explore the path/bridge between two ideas.

        Args:
            source_node: The name or UUID of the starting concept node.
            target_node: The name or UUID of the target concept node.
        """
        if not source_node or not target_node:
            return {"error": "Both source_node and target_node are required"}

        res = _run(
            graph_client.find_path(
                project_id,
                jwt_token,
                source=source_node.strip(),
                target=target_node.strip(),
                max_depth=6,
            )
        )
        if not isinstance(res, dict):
            return {"error": "Failed to retrieve path"}

        nodes = res.get("nodes", [])
        edges = res.get("edges", [])
        bridge_nodes = res.get("bridgeNodes", [])

        if not nodes:
            return {
                "found": False,
                "message": f"No path found between '{source_node}' and '{target_node}' within 6 hops.",
                "source": source_node,
                "target": target_node,
            }

        node_ids = [n.get("nodeId") for n in nodes if n.get("nodeId")]
        edge_ids = [e.get("edgeId") for e in edges if e.get("edgeId")]

        # Record into metadata tracker for SSE emission
        path_data = {
            "source": source_node,
            "target": target_node,
            "nodes": node_ids,
            "nodeIds": node_ids,
            "edges": edge_ids,
            "bridgeNodes": [
                {
                    "nodeId": str(bn.get("nodeId") if isinstance(bn, dict) else bn),
                    "nodeName": str((bn.get("nodeName") or bn.get("nodeId")) if isinstance(bn, dict) else bn),
                }
                for bn in bridge_nodes
                if bn
            ],
        }
        record_path_highlight(project_id, session_id, path_data)

        # Build reasoning path
        reasoning_steps = []
        for i, edge in enumerate(edges):
            src_id = edge.get("sourceNodeId")
            tgt_id = edge.get("targetNodeId")
            props = edge.get("properties")
            is_mention = False
            if isinstance(props, dict):
                is_mention = bool(props.get("isMention"))
            elif isinstance(props, str) and '"isMention":true' in props:
                is_mention = True
            relation_name = "RELATES_TO (wikilink mention)" if is_mention else (edge.get("edgeTypeId") or "RELATES_TO")
            reasoning_steps.append(
                {
                    "step": i + 1,
                    "source": src_id,
                    "target": tgt_id,
                    "relation": relation_name,
                }
            )

        set_metadata(
            project_id,
            session_id,
            {
                "pathHighlight": path_data,
                "reasoningPath": reasoning_steps,
            },
        )

        return {
            "found": True,
            "path_length": len(edges),
            "source_node": nodes[0].get("nodeName") if nodes else source_node,
            "target_node": nodes[-1].get("nodeName") if nodes else target_node,
            "bridge_concepts": [bn.get("nodeName") for bn in bridge_nodes],
            "ordered_path": [n.get("nodeName") for n in nodes],
            "details": [
                {
                    "name": n.get("nodeName"),
                    "note": n.get("note") or "",
                    "data": n.get("data") or {},
                }
                for n in nodes
            ],
        }

    def llm_generate_flashcards(topic: str = "", count: int = 5) -> dict:
        """Generate active-recall flashcards from graph concepts.

        Args:
            topic: Optional concept name or topic used to select graph nodes.
            count: Number of cards to generate, from 1 to 20.
        """
        safe_count = max(1, min(20, int(count or 5)))
        query = (topic or "").strip().lower()
        nodes = _run(graph_client.get_nodes(project_id, jwt_token))
        if not isinstance(nodes, list):
            return {"error": "Failed to retrieve graph nodes"}

        if query:
            selected = [
                node for node in nodes
                if query in str(node.get("nodeName", "")).lower()
                or query in str(node.get("note", "")).lower()
            ]
        else:
            selected = nodes
        node_ids = [extract_node_id(node) for node in selected if extract_node_id(node)]
        if not node_ids:
            return {"cards": [], "total": 0, "message": "No matching graph concepts found"}

        from app.services.flashcard_generator import generate_flashcards_from_nodes

        cards = _run(
            generate_flashcards_from_nodes(
                project_id=project_id,
                node_ids=node_ids,
                count=safe_count,
                jwt_token=jwt_token,
                graph_client=graph_client,
            )
        )
        return {"cards": cards, "total": len(cards), "topic": topic or "all"}

    return [
        llm_get_all_nodes,
        llm_get_all_edges,
        llm_query_graph,
        llm_traverse_graph,
        llm_find_path,
        llm_generate_flashcards,
        llm_glob_files,
        llm_grep_search,
        llm_read_file_content,
        llm_create_node,
        llm_update_node,
        llm_update_node_note,
        llm_delete_node,
        llm_create_edge,
        llm_update_edge,
        llm_delete_edge,
        llm_list_node_types,
        llm_list_files,
        llm_read_file,
        llm_highlight,
    ]
