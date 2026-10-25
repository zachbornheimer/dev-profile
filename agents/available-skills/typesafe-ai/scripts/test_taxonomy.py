"""Behavior tests for the taxonomy.json loader/validator (design section 1.2)."""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

taxonomy = importlib.import_module("taxonomy")


def area(node_id: str = "area:homelab", **overrides: object) -> dict:
    node = {
        "id": node_id,
        "parent": None,
        "depth": 1,
        "type": "area",
        "label": "Homelab & NAS",
        "criteria": "Homelab, NAS, and self-hosted infrastructure.",
        "tokens": ["homelab", "nas"],
    }
    node.update(overrides)
    return node


def product(
    node_id: str = "product:homelab", parent: str = "area:homelab", **overrides: object
) -> dict:
    node = {
        "id": node_id,
        "parent": parent,
        "depth": 2,
        "type": "product",
        "label": "homelab",
        "criteria": "Products: homelab, nas-recovery.",
        "tokens": ["homelab"],
    }
    node.update(overrides)
    return node


def leaf(
    node_id: str = "leaf:repo:zachbornheimer/homelab",
    parent: str = "product:homelab",
    project_key: str = "zachbornheimer/homelab",
    **overrides: object,
) -> dict:
    node = {
        "id": node_id,
        "parent": parent,
        "depth": 3,
        "type": "leaf",
        "leaf_kind": "repo",
        "label": "homelab",
        "criteria": "Docker-compose homelab and NAS automation.",
        "project_key": project_key,
        "local_path": "/Users/zbornheimer/Developer/Personal/homelab",
        "tokens": ["homelab"],
    }
    node.update(overrides)
    return node


def payload(nodes: list[dict], **overrides: object) -> dict:
    document = {
        "schema_version": 1,
        "taxonomy_version": "1.ab12cd34ef56",
        "generated_at": "2026-09-23T00:00:00Z",
        "nodes": nodes,
    }
    document.update(overrides)
    return document


VALID_TREE = [area(), product(), leaf()]


class ParseTaxonomyTests(unittest.TestCase):
    def test_a_valid_tree_parses_into_navigable_nodes(self) -> None:
        result = taxonomy.parse_taxonomy(payload(VALID_TREE))
        self.assertEqual(result.taxonomy_version, "1.ab12cd34ef56")
        self.assertEqual({node.id for node in result.areas()}, {"area:homelab"})
        self.assertEqual(
            {node.id for node in result.children_of("area:homelab")}, {"product:homelab"}
        )
        self.assertEqual(
            result.node("leaf:repo:zachbornheimer/homelab").project_key, "zachbornheimer/homelab"
        )

    def test_unknown_schema_version_raises(self) -> None:
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(VALID_TREE, schema_version=2))

    def test_duplicate_id_raises(self) -> None:
        nodes = [area(), product(), leaf(), leaf(node_id="leaf:repo:zachbornheimer/homelab")]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_orphan_parent_raises(self) -> None:
        nodes = [area(), product(parent="area:does-not-exist"), leaf()]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_wrong_depth_for_parent_raises(self) -> None:
        nodes = [area(), product(depth=3), leaf()]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_leaf_not_at_depth_three_raises(self) -> None:
        nodes = [area(), product(), leaf(depth=2)]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_empty_criteria_raises(self) -> None:
        nodes = [area(criteria=""), product(), leaf()]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_criteria_over_the_length_cap_raises(self) -> None:
        nodes = [area(criteria="x" * 181), product(), leaf()]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_non_leaf_with_no_children_raises(self) -> None:
        nodes = [area(), product()]  # product has no leaf child
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_duplicate_project_key_across_leaves_raises(self) -> None:
        nodes = [
            area(),
            product(),
            leaf(),
            leaf(
                node_id="leaf:linear:Homelab",
                leaf_kind="linear",
                project_key="zachbornheimer/homelab",
                local_path=None,
            ),
        ]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))

    def test_more_than_the_area_cap_raises(self) -> None:
        areas = [area(node_id=f"area:a{i}") for i in range(11)]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(areas))

    def test_unknown_node_type_raises(self) -> None:
        nodes = [area(type="galaxy"), product(), leaf()]
        with self.assertRaises(ValueError):
            taxonomy.parse_taxonomy(payload(nodes))


class LoadTaxonomyTests(unittest.TestCase):
    def test_loads_a_valid_file_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "taxonomy.json"
            path.write_text(json.dumps(payload(VALID_TREE)), encoding="utf-8")
            result = taxonomy.load_taxonomy(str(path))
            self.assertEqual(result.schema_version, 1)

    def test_missing_file_raises_oserror(self) -> None:
        with self.assertRaises(OSError):
            taxonomy.load_taxonomy("/nonexistent/taxonomy.json")

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "taxonomy.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                taxonomy.load_taxonomy(str(path))

    def test_non_object_payload_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "taxonomy.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                taxonomy.load_taxonomy(str(path))


if __name__ == "__main__":
    unittest.main()
