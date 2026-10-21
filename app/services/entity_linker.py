"""Entity Linker and Deduplication service using RapidFuzz token_set_ratio."""
from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process

from app.clients.graph_client import extract_node_id


class TripleItem(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0


class EntityResolutionResult(BaseModel):
    resolved_id: str
    canonical_name: str
    is_new: bool
    fuzzy_score: float


class EntityLinker:
    """Entity Linker & Deduplication using RapidFuzz token_set_ratio."""

    def __init__(self, threshold: float = 85.0):
        self.threshold = threshold

    def resolve_entity(
        self,
        candidate_name: str,
        existing_nodes: list[dict[str, Any]],
    ) -> EntityResolutionResult:
        """Resolve candidate entity against existing nodes using RapidFuzz token_set_ratio.

        If match score >= threshold: returns existing node's id and canonical name, is_new=False.
        If match score < threshold or no match: returns new UUID and candidate name, is_new=True.
        """
        cand = (candidate_name or "").strip()
        if not cand:
            return EntityResolutionResult(
                resolved_id=str(uuid.uuid4()),
                canonical_name="",
                is_new=True,
                fuzzy_score=0.0,
            )

        name_to_node: dict[str, dict[str, Any]] = {}
        for node in existing_nodes:
            if not isinstance(node, dict):
                continue
            name = str(node.get("nodeName") or node.get("name") or node.get("title") or "").strip()
            if name and name not in name_to_node:
                name_to_node[name] = node

        choices = list(name_to_node.keys())
        if not choices:
            return EntityResolutionResult(
                resolved_id=str(uuid.uuid4()),
                canonical_name=cand,
                is_new=True,
                fuzzy_score=0.0,
            )

        match = process.extractOne(
            cand,
            choices,
            scorer=fuzz.token_set_ratio,
        )

        if match is not None:
            best_choice, score, _idx = match
            score_float = float(score)
            if score_float >= self.threshold:
                matched_node = name_to_node[best_choice]
                node_id = extract_node_id(matched_node) or str(uuid.uuid4())
                return EntityResolutionResult(
                    resolved_id=node_id,
                    canonical_name=best_choice,
                    is_new=False,
                    fuzzy_score=score_float,
                )
            else:
                return EntityResolutionResult(
                    resolved_id=str(uuid.uuid4()),
                    canonical_name=cand,
                    is_new=True,
                    fuzzy_score=score_float,
                )

        return EntityResolutionResult(
            resolved_id=str(uuid.uuid4()),
            canonical_name=cand,
            is_new=True,
            fuzzy_score=0.0,
        )

    def link_and_deduplicate_concepts(
        self,
        concepts: dict[str, Any],
        existing_nodes: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[EntityResolutionResult]]:
        """Link and deduplicate nodes, edges, and triples against existing nodes.

        Updates nodes with resolved IDs, preserves new nodes, remaps edges/triples.
        Maintains dynamic cache of newly created nodes in this batch so internal duplicates merge.
        """
        working_nodes = list(existing_nodes)
        resolved_results: list[EntityResolutionResult] = []
        name_mapping: dict[str, EntityResolutionResult] = {}

        raw_nodes = concepts.get("nodes", [])
        linked_nodes: list[dict[str, Any]] = []

        for node in raw_nodes:
            cand_name = str(node.get("title") or node.get("nodeName") or "").strip()
            if not cand_name:
                continue
            if cand_name in name_mapping:
                res = name_mapping[cand_name]
            else:
                res = self.resolve_entity(cand_name, working_nodes)
                name_mapping[cand_name] = res
                resolved_results.append(res)
                if res.is_new:
                    new_entry = {
                        "nodeId": res.resolved_id,
                        "nodeName": res.canonical_name,
                        "title": res.canonical_name,
                        "note": node.get("description", ""),
                    }
                    working_nodes.append(new_entry)

            node_copy = dict(node)
            node_copy["nodeId"] = res.resolved_id
            node_copy["title"] = res.canonical_name
            node_copy["is_new"] = res.is_new
            linked_nodes.append(node_copy)

        raw_edges = concepts.get("edges", [])
        linked_edges: list[dict[str, Any]] = []
        for edge in raw_edges:
            src = str(edge.get("source") or "").strip()
            tgt = str(edge.get("target") or "").strip()
            if not src or not tgt:
                continue

            if src not in name_mapping:
                res_src = self.resolve_entity(src, working_nodes)
                name_mapping[src] = res_src
                resolved_results.append(res_src)
                if res_src.is_new:
                    working_nodes.append({"nodeId": res_src.resolved_id, "nodeName": res_src.canonical_name})
            else:
                res_src = name_mapping[src]

            if tgt not in name_mapping:
                res_tgt = self.resolve_entity(tgt, working_nodes)
                name_mapping[tgt] = res_tgt
                resolved_results.append(res_tgt)
                if res_tgt.is_new:
                    working_nodes.append({"nodeId": res_tgt.resolved_id, "nodeName": res_tgt.canonical_name})
            else:
                res_tgt = name_mapping[tgt]

            edge_copy = dict(edge)
            edge_copy["source"] = res_src.canonical_name
            edge_copy["target"] = res_tgt.canonical_name
            edge_copy["sourceNodeId"] = res_src.resolved_id
            edge_copy["targetNodeId"] = res_tgt.resolved_id
            linked_edges.append(edge_copy)

        raw_triples = concepts.get("triples", [])
        linked_triples: list[dict[str, Any]] = []
        for triple in raw_triples:
            subj = str(triple.get("subject") or "").strip()
            obj = str(triple.get("object") or "").strip()
            if not subj or not obj:
                continue
            res_subj = name_mapping.get(subj) or self.resolve_entity(subj, working_nodes)
            res_obj = name_mapping.get(obj) or self.resolve_entity(obj, working_nodes)
            triple_copy = dict(triple)
            triple_copy["subject"] = res_subj.canonical_name
            triple_copy["object"] = res_obj.canonical_name
            linked_triples.append(triple_copy)

        return {
            "nodes": linked_nodes,
            "edges": linked_edges,
            "triples": linked_triples,
        }, resolved_results


_default_linker = EntityLinker(threshold=85.0)


def resolve_entity(
    candidate_name: str,
    existing_nodes: list[dict[str, Any]],
    threshold: float = 85.0,
) -> EntityResolutionResult:
    """Convenience functional interface for resolving a single entity."""
    linker = EntityLinker(threshold=threshold) if threshold != 85.0 else _default_linker
    return linker.resolve_entity(candidate_name, existing_nodes)
