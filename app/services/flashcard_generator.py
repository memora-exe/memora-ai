"""Graph RAG Flashcard Synthesizer.

Generates pedagogically sound flashcards (Q&A pairs) from graph nodes and their
relationships using LLM generation with graceful deterministic heuristic fallback.
"""
from __future__ import annotations

import json
import logging
from app.clients.graph_client import GraphClient, extract_node_id, extract_edge_endpoints
from app.services.llm import get_chat_model
from app.services.llm.response_parser import parse_llm_json

logger = logging.getLogger(__name__)


def _generate_heuristic_fallback(
    selected_nodes: list[dict],
    relation_pairs: list[tuple[dict, dict, str]],
    count: int,
) -> list[dict]:
    """Deterministic heuristic generator as graceful fallback."""
    relation_cards = []
    for source, target, relation in relation_pairs:
        source_name = source.get("nodeName", "A")
        target_name = target.get("nodeName", "B")
        if relation == "PREREQUISITE":
            front = f"Trước khi học '{target_name}', cần nắm khái niệm nào?"
            back = f"'{source_name}' là khái niệm tiên quyết cho '{target_name}'."
        elif relation in {"DEFINES", "IS_A"}:
            front = f"'{source_name}' định nghĩa hoặc mô tả gì về '{target_name}'?"
            back = f"Mối quan hệ {relation}: '{source_name}' liên kết với '{target_name}'."
        else:
            front = f"'{source_name}' liên hệ thế nào với '{target_name}'?"
            back = f"'{source_name}' và '{target_name}' có quan hệ {relation}."
        relation_cards.append({
            "front": front,
            "back": back,
            "nodeId": extract_node_id(source),
            "sourceRelation": relation,
        })

    cards: list[dict] = list(relation_cards[:count])
    if len(cards) >= count:
        return cards[:count]

    for node in selected_nodes:
        if len(cards) >= count:
            break
        nid = extract_node_id(node)
        name = node.get("nodeName") or "Concept"
        note = (node.get("note") or "").strip()
        data = node.get("data") or {}

        if note:
            front = f"Định nghĩa và vai trò cốt lõi của khái niệm '{name}' là gì?"
            back = note
        elif data:
            summary = ", ".join(f"{k}: {v}" for k, v in data.items() if v)
            front = f"Đặc điểm chính của '{name}' bao gồm những gì?"
            back = summary or f"'{name}' là một khái niệm thành phần trong hệ thống tri thức."
        else:
            front = f"Giải thích khái niệm '{name}' và ứng dụng của nó?"
            back = f"'{name}' là một khái niệm quan trọng trong hệ thống tri thức của đồ thị."

        cards.append({
            "front": front,
            "back": back,
            "nodeId": nid,
            "sourceRelation": "DEFINES",
        })

    if len(cards) < count and len(selected_nodes) >= 2:
        for i in range(len(selected_nodes) - 1):
            n1 = selected_nodes[i]
            n2 = selected_nodes[i + 1]
            n1_name = n1.get("nodeName", "A")
            n2_name = n2.get("nodeName", "B")
            cards.append({
                "front": f"Mối liên hệ hoặc sự khác biệt chính giữa '{n1_name}' và '{n2_name}' là gì?",
                "back": f"'{n1_name}' và '{n2_name}' là hai khái niệm liên kết trong cùng miền tri thức. Hãy xem xét cách chúng tương tác qua các quan hệ tiên quyết hoặc bổ trợ.",
                "nodeId": extract_node_id(n1),
                "sourceRelation": "RELATES_TO",
            })
            if len(cards) >= count:
                break

    return cards[:count]


async def generate_flashcards_from_nodes(
    project_id: str,
    node_ids: list[str],
    count: int,
    jwt_token: str,
    graph_client: GraphClient,
    prompt: str | None = None,
) -> list[dict]:
    """Generate structured flashcard items from specified node IDs using LLM or heuristic fallback."""
    logger.info(
        "Generating %d flashcards for project %s across %d nodes (has_prompt=%s)",
        count,
        project_id,
        len(node_ids),
        bool(prompt),
    )

    try:
        all_nodes = await graph_client.get_nodes(project_id, jwt_token)
    except Exception as exc:
        logger.warning("Failed to fetch nodes for flashcard generation: %s", exc)
        all_nodes = []

    target_node_ids = set(node_ids)
    selected_nodes = [
        n for n in all_nodes if extract_node_id(n) in target_node_ids
    ]

    try:
        all_edges = await graph_client.get_edges(project_id, jwt_token)
    except Exception as exc:
        logger.warning("Failed to fetch edges for flashcard generation: %s", exc)
        all_edges = []

    node_by_id = {extract_node_id(n): n for n in selected_nodes if extract_node_id(n)}
    relation_pairs = []
    for edge in all_edges:
        source_id, target_id = extract_edge_endpoints(edge)
        if source_id not in node_by_id or target_id not in node_by_id:
            continue
        relation = (
            edge.get("edgeTypeId")
            or (edge.get("properties") or {}).get("edgeTypeId")
            or (edge.get("properties") or {}).get("type")
            or "RELATES_TO"
        )
        relation_pairs.append((node_by_id[source_id], node_by_id[target_id], str(relation).upper()))

    # Try LLM generation first
    try:
        nodes_context = []
        for n in selected_nodes:
            nid = extract_node_id(n)
            name = n.get("nodeName") or "Unknown"
            note = n.get("note") or ""
            nodes_context.append(f"- ID: {nid}\n  Name: {name}\n  Note: {note}")

        edges_context = []
        for s, t, rel in relation_pairs:
            edges_context.append(
                f"- ({s.get('nodeName')}) -[{rel}]-> ({t.get('nodeName')}) [sourceId: {extract_node_id(s)}]"
            )

        context_str = "Selected Concepts/Nodes:\n" + ("\n".join(nodes_context) if nodes_context else "None")
        if edges_context:
            context_str += "\n\nRelationships:\n" + "\n".join(edges_context)

        user_instruction = f"\nAdditional pedagogical instructions from user:\n{prompt.strip()}\n" if prompt and prompt.strip() else ""

        llm_prompt = (
            "You are a master educator and spaced-repetition flashcard author.\n"
            f"Generate exactly {count} high-quality, pedagogically effective flashcards based on the knowledge graph context below.\n"
            "Flashcards must test deep understanding, mechanisms, comparisons, problem scenarios, or definitions.\n"
            f"{user_instruction}\n"
            "Output MUST be valid JSON with this schema:\n"
            "{\n"
            '  "cards": [\n'
            '    {\n'
            '      "front": "Question or prompt",\n'
            '      "back": "Clear, comprehensive answer",\n'
            '      "nodeId": "UUID of corresponding node from context",\n'
            '      "sourceRelation": "RELATES_TO or DEFINES or PREREQUISITE"\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            f"Knowledge Graph Context:\n{context_str}\n"
        )

        llm = get_chat_model(temperature=0.3)
        res = llm.invoke(llm_prompt)
        parsed = parse_llm_json(res, fallback={})

        valid_cards = []
        if isinstance(parsed, dict) and "cards" in parsed and isinstance(parsed["cards"], list):
            for c in parsed["cards"]:
                front = str(c.get("front") or "").strip()
                back = str(c.get("back") or "").strip()
                node_id = str(c.get("nodeId") or "").strip()
                if not node_id and selected_nodes:
                    node_id = extract_node_id(selected_nodes[0]) or ""
                rel = str(c.get("sourceRelation") or "DEFINES").strip()
                if front and back:
                    valid_cards.append({
                        "front": front,
                        "back": back,
                        "nodeId": node_id,
                        "sourceRelation": rel,
                    })

        if valid_cards:
            logger.info("Generated %d cards via LLM synthesizer", len(valid_cards))
            return valid_cards[:count]
    except Exception as exc:
        logger.warning("LLM flashcard generation failed, falling back to heuristic: %s", exc)

    return _generate_heuristic_fallback(selected_nodes, relation_pairs, count)
