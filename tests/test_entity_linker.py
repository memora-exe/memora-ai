"""Unit tests for Entity Linker and Deduplication with RapidFuzz."""
import unittest
from app.services.entity_linker import (
    EntityLinker,
    EntityResolutionResult,
    TripleItem,
    resolve_entity,
)


class TestEntityLinker(unittest.TestCase):
    def setUp(self):
        self.existing_nodes = [
            {"nodeId": "node-1", "nodeName": "Authentication System", "note": "Handles auth"},
            {"nodeId": "node-2", "nodeName": "Database Pool", "note": "Connection pool"},
            {"nodeId": "node-3", "nodeName": "PostgreSQL", "note": "Relational DB"},
        ]
        self.linker = EntityLinker(threshold=85.0)

    def test_exact_match(self):
        result = self.linker.resolve_entity("Authentication System", self.existing_nodes)
        self.assertFalse(result.is_new)
        self.assertEqual(result.resolved_id, "node-1")
        self.assertEqual(result.canonical_name, "Authentication System")
        self.assertAlmostEqual(result.fuzzy_score, 100.0)

    def test_fuzzy_match_above_threshold(self):
        # "Authentication System" with minor token variant
        result = self.linker.resolve_entity("System Authentication", self.existing_nodes)
        self.assertFalse(result.is_new)
        self.assertEqual(result.resolved_id, "node-1")
        self.assertGreaterEqual(result.fuzzy_score, 85.0)

    def test_match_below_threshold(self):
        result = self.linker.resolve_entity("Message Queue RabbitMQ", self.existing_nodes)
        self.assertTrue(result.is_new)
        self.assertNotEqual(result.resolved_id, "node-1")
        self.assertNotEqual(result.resolved_id, "node-2")
        self.assertNotEqual(result.resolved_id, "node-3")
        self.assertLess(result.fuzzy_score, 85.0)

    def test_empty_existing_nodes(self):
        result = self.linker.resolve_entity("PostgreSQL", [])
        self.assertTrue(result.is_new)
        self.assertEqual(result.canonical_name, "PostgreSQL")
        self.assertEqual(result.fuzzy_score, 0.0)

    def test_empty_candidate_name(self):
        result = self.linker.resolve_entity("", self.existing_nodes)
        self.assertTrue(result.is_new)
        self.assertEqual(result.canonical_name, "")
        self.assertEqual(result.fuzzy_score, 0.0)

    def test_link_and_deduplicate_concepts(self):
        concepts = {
            "nodes": [
                {"title": "PostgreSQL", "description": "Relational DB"},
                {"title": "Redis Cache", "description": "In-memory cache"},
            ],
            "edges": [
                {"source": "PostgreSQL", "target": "Redis Cache", "type": "CONNECTS_TO"}
            ],
            "triples": [
                {"subject": "PostgreSQL", "predicate": "CONNECTS_TO", "object": "Redis Cache"}
            ]
        }
        linked, resolutions = self.linker.link_and_deduplicate_concepts(concepts, self.existing_nodes)

        # PostgreSQL maps to existing node-3
        pg_node = next(n for n in linked["nodes"] if n["title"] == "PostgreSQL")
        self.assertFalse(pg_node["is_new"])
        self.assertEqual(pg_node["nodeId"], "node-3")

        # Redis Cache is new
        redis_node = next(n for n in linked["nodes"] if n["title"] == "Redis Cache")
        self.assertTrue(redis_node["is_new"])

        # Edge maps correctly
        edge = linked["edges"][0]
        self.assertEqual(edge["sourceNodeId"], "node-3")
        self.assertEqual(edge["targetNodeId"], redis_node["nodeId"])

    def test_triple_item_model(self):
        t = TripleItem(subject="A", predicate="RELATES_TO", object="B")
        self.assertEqual(t.subject, "A")
        self.assertEqual(t.predicate, "RELATES_TO")
        self.assertEqual(t.object, "B")
        self.assertEqual(t.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
