"""Taxonomy loader and validator for `organize-files/data/taxonomy.json` (schema v1).

The classifier only loads and validates the taxonomy; it never builds one — the
builder (`organize-files/scripts/build_taxonomy.py`) owns derivation. Keeping load
deterministic and separate from derivation makes taxonomy loading/versioning
reviewable on its own (typesafe-skills example 26): a bad build never reaches the
classifier silently, because `load_taxonomy`/`parse_taxonomy` raise on any schema
violation and the caller falls back to flat mode with `REASON_FILE_TAXONOMY_INVALID`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from constants import (
    DESCRIPTION_CHARS,
    FILE_TAXONOMY_MAX_AREAS,
    FILE_TAXONOMY_SCHEMA_VERSION,
)

TAXONOMY_NODE_TYPE_AREA = "area"
TAXONOMY_NODE_TYPE_PRODUCT = "product"
TAXONOMY_NODE_TYPE_LEAF = "leaf"
TAXONOMY_NODE_TYPES = frozenset(
    {TAXONOMY_NODE_TYPE_AREA, TAXONOMY_NODE_TYPE_PRODUCT, TAXONOMY_NODE_TYPE_LEAF}
)
TAXONOMY_ROOT_LEVEL_DEPTH = 1
TAXONOMY_LEAF_DEPTH = 3


class TaxonomyInvalid(ValueError):
    """A taxonomy.json payload or node failed schema validation. A `ValueError`
    subclass so every existing `except ValueError` fallback (design section 1.2)
    still catches it, while staying distinct from Python's builtin "wrong Python
    type" convention for a malformed *domain* payload."""


@dataclass(frozen=True, slots=True)
class TaxonomyNode:
    """One node of the flat, parent-pointer taxonomy tree (design section 1.2)."""

    id: str
    parent: str | None
    depth: int
    type: str
    label: str
    criteria: str
    tokens: tuple[str, ...] = ()
    leaf_kind: str | None = None
    project_key: str | None = None
    local_path: str | None = None
    destination: str | None = None
    aliases: tuple[str, ...] = ()
    archived: bool = False
    large: bool = False
    derived_by: str | None = None


@dataclass(frozen=True, slots=True)
class Taxonomy:
    """A validated taxonomy: every id is unique, every parent resolves, every leaf
    sits at depth 3, and node count stays within `FILE_TAXONOMY_MAX_AREAS` at the
    root. Callers navigate it by id — `parse_taxonomy`/`load_taxonomy` are the only
    ways to construct one, so an unvalidated instance cannot exist."""

    schema_version: int
    taxonomy_version: str
    generated_at: str
    nodes: dict[str, TaxonomyNode] = field(default_factory=dict)

    def node(self, node_id: str) -> TaxonomyNode:
        return self.nodes[node_id]

    def children_of(self, node_id: str | None) -> list[TaxonomyNode]:
        return [node for node in self.nodes.values() if node.parent == node_id]

    def areas(self) -> list[TaxonomyNode]:
        return [node for node in self.nodes.values() if node.type == TAXONOMY_NODE_TYPE_AREA]


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _optional_str(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def _node_from_json(raw: object) -> TaxonomyNode:
    if not isinstance(raw, dict):
        raise TaxonomyInvalid("taxonomy node must be an object")
    node_id = str(raw.get("id") or "")
    if not node_id:
        raise ValueError("taxonomy node missing id")
    node_type = str(raw.get("type") or "")
    if node_type not in TAXONOMY_NODE_TYPES:
        raise ValueError(f"taxonomy node {node_id} has unknown type {node_type!r}")
    try:
        depth = int(raw.get("depth"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"taxonomy node {node_id} has a non-integer depth") from exc
    return TaxonomyNode(
        id=node_id,
        parent=_optional_str(raw.get("parent")),
        depth=depth,
        type=node_type,
        label=str(raw.get("label") or ""),
        criteria=str(raw.get("criteria") or ""),
        tokens=_string_tuple(raw.get("tokens")),
        leaf_kind=_optional_str(raw.get("leaf_kind")),
        project_key=_optional_str(raw.get("project_key")),
        local_path=_optional_str(raw.get("local_path")),
        destination=_optional_str(raw.get("destination")),
        aliases=_string_tuple(raw.get("aliases")),
        archived=bool(raw.get("archived", False)),
        large=bool(raw.get("large", False)),
        derived_by=_optional_str(raw.get("derived_by")),
    )


def _validate_structure(nodes: dict[str, TaxonomyNode]) -> None:
    child_counts: dict[str, int] = {}
    project_keys: set[str] = set()
    for node in nodes.values():
        if node.parent is None:
            if node.depth != TAXONOMY_ROOT_LEVEL_DEPTH:
                raise ValueError(f"taxonomy root-level node {node.id} must be depth 1")
        else:
            parent = nodes.get(node.parent)
            if parent is None:
                raise ValueError(f"taxonomy node {node.id} has orphan parent {node.parent}")
            if node.depth != parent.depth + 1:
                raise ValueError(f"taxonomy node {node.id} depth does not follow its parent")
            child_counts[node.parent] = child_counts.get(node.parent, 0) + 1
        if node.type == TAXONOMY_NODE_TYPE_LEAF and node.depth != TAXONOMY_LEAF_DEPTH:
            raise ValueError(f"taxonomy leaf {node.id} must be at depth {TAXONOMY_LEAF_DEPTH}")
        if not node.criteria or len(node.criteria) > DESCRIPTION_CHARS:
            raise ValueError(f"taxonomy node {node.id} criteria empty or over the length cap")
        if node.project_key:
            if node.project_key in project_keys:
                raise ValueError(f"duplicate taxonomy project_key {node.project_key!r}")
            project_keys.add(node.project_key)
    for node in nodes.values():
        if node.type != TAXONOMY_NODE_TYPE_LEAF and child_counts.get(node.id, 0) == 0:
            raise ValueError(f"taxonomy non-leaf node {node.id} has no children")
    area_count = sum(1 for node in nodes.values() if node.type == TAXONOMY_NODE_TYPE_AREA)
    if area_count > FILE_TAXONOMY_MAX_AREAS:
        raise ValueError(f"taxonomy has {area_count} areas, over FILE_TAXONOMY_MAX_AREAS")


def parse_taxonomy(payload: dict[str, Any]) -> Taxonomy:
    """Validate a decoded taxonomy.json payload and build a `Taxonomy`. Raises
    `ValueError` on the first violation (design section 1.2's validator contract);
    the caller falls back to flat mode with `REASON_FILE_TAXONOMY_INVALID`."""
    schema_version = payload.get("schema_version")
    if schema_version != FILE_TAXONOMY_SCHEMA_VERSION:
        raise ValueError(f"taxonomy schema_version unknown: {schema_version!r}")
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("taxonomy nodes missing or empty")
    nodes: dict[str, TaxonomyNode] = {}
    for raw_node in raw_nodes:
        node = _node_from_json(raw_node)
        if node.id in nodes:
            raise ValueError(f"duplicate taxonomy node id {node.id!r}")
        nodes[node.id] = node
    _validate_structure(nodes)
    return Taxonomy(
        schema_version=schema_version,
        taxonomy_version=str(payload.get("taxonomy_version") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        nodes=nodes,
    )


def load_taxonomy(path: str) -> Taxonomy:
    """Read, parse, and validate taxonomy.json from disk. Raises `OSError`/
    `ValueError` on any I/O, JSON, or schema problem — never returns a partially
    valid taxonomy."""
    raw = Path(path).expanduser().read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TaxonomyInvalid("taxonomy payload is not an object")
    return parse_taxonomy(payload)
