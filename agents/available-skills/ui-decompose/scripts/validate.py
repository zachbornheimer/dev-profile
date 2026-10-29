#!/usr/bin/env python3
"""Validate UI decomposition workflow artifacts.

The validator enforces schema shape, graph integrity, audit coverage, artifact
binding, and correction accountability. It does not claim to infer UI content;
that remains the job of independent source-inspecting agents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SCHEMA_DIR = SKILL_DIR / "schemas"


class Issues:
    """Collect validation failures while allowing a complete diagnostic pass."""

    def __init__(self) -> None:
        self._items: list[str] = []

    def add(self, message: str) -> None:
        self._items.append(message)

    def extend(self, messages: Iterable[str]) -> None:
        self._items.extend(messages)

    @property
    def items(self) -> list[str]:
        return self._items

    def __bool__(self) -> bool:
        return bool(self._items)


def load_json(path: Path) -> Any:
    """Load a JSON document with a concise error on malformed input."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for an artifact exactly as stored on disk."""

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path}") from exc


def schema_issues(data: Any, schema_path: Path) -> list[str]:
    """Return stable, path-qualified JSON Schema errors."""

    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(data), key=lambda error: list(error.absolute_path)
    )

    result: list[str] = []
    for error in errors:
        location = "$"
        for part in error.absolute_path:
            location += f"[{part}]" if isinstance(part, int) else f".{part}"
        result.append(f"schema {location}: {error.message}")
    return result


def index_by_id(
    items: list[dict[str, Any]], label: str, issues: Issues
) -> dict[str, dict[str, Any]]:
    """Index entities and report duplicate IDs within a collection."""

    result: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item["id"]
        if item_id in result:
            issues.add(f"duplicate {label} id: {item_id}")
        else:
            result[item_id] = item
    return result


def detect_parent_cycle(
    entities: dict[str, dict[str, Any]], parent_field: str, label: str, issues: Issues
) -> None:
    """Detect cycles in a nullable parent graph."""

    for entity_id in entities:
        seen: set[str] = set()
        current: str | None = entity_id
        while current is not None:
            if current in seen:
                issues.add(f"{label} parent cycle includes: {current}")
                break
            seen.add(current)
            entity = entities.get(current)
            if entity is None:
                break
            current = entity.get(parent_field)


def exact_set(
    label: str, declared: Iterable[str], actual: Iterable[str], issues: Issues
) -> None:
    """Require a coverage declaration to equal the actual entity set."""

    declared_set = set(declared)
    actual_set = set(actual)
    missing = sorted(actual_set - declared_set)
    extra = sorted(declared_set - actual_set)
    if missing:
        issues.add(f"{label} missing: {', '.join(missing)}")
    if extra:
        issues.add(f"{label} contains unknown/extra ids: {', '.join(extra)}")


def state_surface_id(
    state: dict[str, Any], nodes: dict[str, dict[str, Any]]
) -> str | None:
    """Resolve the surface containing a state."""

    if state["ownerType"] == "surface":
        return state["ownerId"]
    owner = nodes.get(state["ownerId"])
    return owner["surfaceId"] if owner is not None else None


def surface_entity_sets(
    surface_id: str,
    nodes: dict[str, dict[str, Any]],
    states: dict[str, dict[str, Any]],
    interactions: dict[str, dict[str, Any]],
) -> tuple[set[str], set[str], set[str]]:
    """Return node/state/interaction IDs belonging to one surface."""

    node_ids = {
        node_id for node_id, node in nodes.items() if node["surfaceId"] == surface_id
    }
    state_ids = {
        state_id
        for state_id, state in states.items()
        if (state["ownerType"] == "surface" and state["ownerId"] == surface_id)
        or (state["ownerType"] == "node" and state["ownerId"] in node_ids)
    }
    interaction_ids = {
        interaction_id
        for interaction_id, interaction in interactions.items()
        if interaction["sourceNodeId"] in node_ids
    }
    return node_ids, state_ids, interaction_ids


def validate_decomposition_invariants(
    data: dict[str, Any], certify: bool, request_path: Path | None = None
) -> Issues:
    """Validate graph integrity, declared coverage, artifact binding, and certification."""

    issues = Issues()

    if request_path is not None:
        expected_request_digest = sha256_file(request_path)
        if data["requestSha256"] != expected_request_digest:
            issues.add(
                f"decomposition request digest mismatch: expected {expected_request_digest}, "
                f"found {data['requestSha256']}"
            )

    surfaces = index_by_id(data["surfaces"], "surface", issues)
    nodes = index_by_id(data["nodes"], "node", issues)
    states = index_by_id(data["states"], "state", issues)
    interactions = index_by_id(data["interactions"], "interaction", issues)
    unresolved = index_by_id(data["unresolved"], "unresolved", issues)

    # IDs are globally unique so every reference is unambiguous.
    global_ids: dict[str, str] = {}
    for label, collection in (
        ("surface", surfaces),
        ("node", nodes),
        ("state", states),
        ("interaction", interactions),
        ("unresolved", unresolved),
    ):
        for entity_id in collection:
            previous = global_ids.get(entity_id)
            if previous is not None:
                issues.add(
                    f"global id collision: {entity_id} is both {previous} and {label}"
                )
            else:
                global_ids[entity_id] = label

    # Every entry file must be recorded exactly once as inspected.
    file_records = data["source"]["filesRead"]
    file_paths: set[str] = set()
    inspected_file_paths: set[str] = set()
    for record in file_records:
        path = record["path"]
        if path in file_paths:
            issues.add(f"duplicate source.filesRead path: {path}")
        file_paths.add(path)
        if record["inspected"]:
            inspected_file_paths.add(path)

    for entry in data["source"]["entryFiles"]:
        if entry not in file_paths:
            issues.add(f"entry file missing from source.filesRead: {entry}")

    # The explicit self-audit ledger must reconcile exactly with inspected source and entities.
    coverage = data["coverage"]
    exact_set(
        "coverage.sourceFilesInspected",
        coverage["sourceFilesInspected"],
        inspected_file_paths,
        issues,
    )
    exact_set("coverage.surfaceIds", coverage["surfaceIds"], surfaces, issues)
    exact_set("coverage.nodeIds", coverage["nodeIds"], nodes, issues)
    exact_set("coverage.stateIds", coverage["stateIds"], states, issues)
    exact_set(
        "coverage.interactionIds", coverage["interactionIds"], interactions, issues
    )

    # Scope roots must exactly match the roots of the surface parent graph.
    actual_root_surfaces = {
        sid for sid, surface in surfaces.items() if surface["parentSurfaceId"] is None
    }
    exact_set(
        "scope.rootSurfaceIds",
        data["scope"]["rootSurfaceIds"],
        actual_root_surfaces,
        issues,
    )

    # Validate surface hierarchy, roots, and trigger edges.
    for surface_id, surface in surfaces.items():
        parent_id = surface["parentSurfaceId"]
        if parent_id is not None and parent_id not in surfaces:
            issues.add(
                f"surface {surface_id} references missing parentSurfaceId {parent_id}"
            )
        if parent_id == surface_id:
            issues.add(f"surface {surface_id} cannot parent itself")

        root_id = surface["rootNodeId"]
        root = nodes.get(root_id)
        if root is None:
            issues.add(f"surface {surface_id} references missing rootNodeId {root_id}")
        else:
            if root["surfaceId"] != surface_id:
                issues.add(
                    f"surface {surface_id} root node {root_id} belongs to {root['surfaceId']}"
                )
            if root["parentId"] is not None:
                issues.add(
                    f"surface {surface_id} root node {root_id} must have parentId=null"
                )

        for interaction_id in surface["triggerInteractionIds"]:
            interaction = interactions.get(interaction_id)
            if interaction is None:
                issues.add(
                    f"surface {surface_id} references missing trigger interaction {interaction_id}"
                )
            elif interaction["targetSurfaceId"] != surface_id:
                issues.add(
                    f"surface {surface_id} trigger {interaction_id} does not target that surface"
                )
            elif interaction["result"] not in {"opens-surface", "navigates-surface"}:
                issues.add(
                    f"surface {surface_id} trigger {interaction_id} must open or navigate to the surface"
                )

    detect_parent_cycle(surfaces, "parentSurfaceId", "surface", issues)

    # Validate node hierarchy, ownership, atomicity, and reciprocal edges.
    nodes_by_surface: dict[str, set[str]] = defaultdict(set)
    for node_id, node in nodes.items():
        surface_id = node["surfaceId"]
        if surface_id not in surfaces:
            issues.add(f"node {node_id} references missing surface {surface_id}")
        else:
            nodes_by_surface[surface_id].add(node_id)

        parent_id = node["parentId"]
        if parent_id is not None:
            parent = nodes.get(parent_id)
            if parent is None:
                issues.add(f"node {node_id} references missing parent {parent_id}")
            else:
                if parent["surfaceId"] != surface_id:
                    issues.add(
                        f"node {node_id} parent {parent_id} belongs to another surface"
                    )
                if node_id not in parent["childIds"]:
                    issues.add(
                        f"node {node_id} parent {parent_id} does not list it in childIds"
                    )

        if node["atomic"] and node["childIds"]:
            issues.add(f"atomic node {node_id} must not have children")
        if not node["atomic"] and not node["childIds"]:
            issues.add(f"non-atomic node {node_id} must have at least one child")
        if node["kind"] == "text" and node["atomic"] and not node["visibleText"]:
            issues.add(f"atomic text node {node_id} must contain visibleText")

        if node["interactive"] and not node["interactionIds"]:
            issues.add(
                f"interactive node {node_id} must define at least one interaction"
            )
        if not node["interactive"] and node["interactionIds"]:
            issues.add(f"non-interactive node {node_id} must not list interactions")

        for child_id in node["childIds"]:
            child = nodes.get(child_id)
            if child is None:
                issues.add(f"node {node_id} references missing child {child_id}")
            else:
                if child["surfaceId"] != surface_id:
                    issues.add(
                        f"node {node_id} child {child_id} belongs to another surface"
                    )
                if child["parentId"] != node_id:
                    issues.add(
                        f"node {node_id} child {child_id} has parentId={child['parentId']!r}"
                    )

        for state_id in node["stateIds"]:
            state = states.get(state_id)
            if state is None:
                issues.add(f"node {node_id} references missing state {state_id}")
            elif state["ownerType"] != "node" or state["ownerId"] != node_id:
                issues.add(f"node {node_id} state {state_id} is not owned by that node")

        for interaction_id in node["interactionIds"]:
            interaction = interactions.get(interaction_id)
            if interaction is None:
                issues.add(
                    f"node {node_id} references missing interaction {interaction_id}"
                )
            elif interaction["sourceNodeId"] != node_id:
                issues.add(
                    f"node {node_id} interaction {interaction_id} has sourceNodeId={interaction['sourceNodeId']}"
                )

    detect_parent_cycle(nodes, "parentId", "node", issues)

    # Every node must be reachable from its surface root; no orphan subtrees are allowed.
    for surface_id, surface_node_ids in nodes_by_surface.items():
        surface = surfaces.get(surface_id)
        if surface is None:
            continue
        root_id = surface["rootNodeId"]
        if root_id not in nodes:
            continue

        reachable: set[str] = set()
        stack = [root_id]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            node = nodes.get(current)
            if node is not None:
                stack.extend(node["childIds"])

        for orphan_id in sorted(surface_node_ids - reachable):
            issues.add(
                f"node {orphan_id} is not reachable from surface {surface_id} root"
            )

        null_parent_nodes = sorted(
            node_id
            for node_id in surface_node_ids
            if nodes[node_id]["parentId"] is None
        )
        if null_parent_nodes != [root_id]:
            issues.add(
                f"surface {surface_id} must have exactly one parentless node ({root_id}); "
                f"found {null_parent_nodes}"
            )

    # Validate state ownership and require exactly one baseline state per surface.
    surface_default_states: dict[str, int] = defaultdict(int)
    for state_id, state in states.items():
        owner_id = state["ownerId"]
        if state["ownerType"] == "surface":
            if owner_id not in surfaces:
                issues.add(
                    f"state {state_id} references missing surface owner {owner_id}"
                )
            if state["kind"] == "default":
                surface_default_states[owner_id] += 1
        else:
            owner = nodes.get(owner_id)
            if owner is None:
                issues.add(f"state {state_id} references missing node owner {owner_id}")
            elif state_id not in owner["stateIds"]:
                issues.add(f"state {state_id} is not listed by owning node {owner_id}")

    for surface_id in surfaces:
        count = surface_default_states[surface_id]
        if count != 1:
            issues.add(
                f"surface {surface_id} must define exactly one default surface state; found {count}"
            )

    # Validate interaction sources, result-specific targets, and reciprocal surface edges.
    unresolved_interaction_ids = {
        item["scopeId"]
        for item in unresolved.values()
        if item["scopeType"] == "interaction" and item["scopeId"] is not None
    }

    for interaction_id, interaction in interactions.items():
        source_id = interaction["sourceNodeId"]
        source = nodes.get(source_id)
        source_surface_id = source["surfaceId"] if source is not None else None
        if source is None:
            issues.add(
                f"interaction {interaction_id} references missing source node {source_id}"
            )
        elif interaction_id not in source["interactionIds"]:
            issues.add(
                f"interaction {interaction_id} is not listed by source node {source_id}"
            )

        target_surface_id = interaction["targetSurfaceId"]
        target_state_id = interaction["targetStateId"]
        result = interaction["result"]

        if target_surface_id is not None and target_surface_id not in surfaces:
            issues.add(
                f"interaction {interaction_id} references missing target surface {target_surface_id}"
            )
        if target_state_id is not None and target_state_id not in states:
            issues.add(
                f"interaction {interaction_id} references missing target state {target_state_id}"
            )

        if result in {"opens-surface", "navigates-surface"}:
            if target_surface_id is None:
                issues.add(
                    f"interaction {interaction_id} result={result} requires targetSurfaceId"
                )
            elif target_surface_id in surfaces:
                target = surfaces[target_surface_id]
                if interaction_id not in target["triggerInteractionIds"]:
                    issues.add(
                        f"interaction {interaction_id} targets {target_surface_id}, but that surface does not list it as a trigger"
                    )
                if (
                    result == "opens-surface"
                    and source_surface_id is not None
                    and target["parentSurfaceId"] != source_surface_id
                ):
                    issues.add(
                        f"interaction {interaction_id} opens {target_surface_id}, whose parentSurfaceId must be {source_surface_id}"
                    )

        if result == "closes-surface":
            if target_surface_id is None:
                issues.add(
                    f"interaction {interaction_id} result=closes-surface requires targetSurfaceId"
                )
            elif (
                source_surface_id is not None and target_surface_id != source_surface_id
            ):
                issues.add(
                    f"interaction {interaction_id} closes {target_surface_id}, but its source is on {source_surface_id}"
                )

        if result == "state-change" and target_state_id is None:
            issues.add(
                f"interaction {interaction_id} result=state-change requires targetStateId"
            )

        if result in {"none", "data-change", "external"}:
            if target_surface_id is not None:
                issues.add(
                    f"interaction {interaction_id} result={result} must not target a UI surface"
                )
            if target_state_id is not None:
                issues.add(
                    f"interaction {interaction_id} result={result} must not target a UI state"
                )

        if target_state_id is not None and target_state_id in states:
            target_state_surface = state_surface_id(states[target_state_id], nodes)
            allowed_surfaces = {
                sid for sid in (source_surface_id, target_surface_id) if sid is not None
            }
            if (
                target_state_surface is not None
                and target_state_surface not in allowed_surfaces
            ):
                issues.add(
                    f"interaction {interaction_id} targets state {target_state_id} on unrelated surface {target_state_surface}"
                )

        if result == "unknown" and interaction_id not in unresolved_interaction_ids:
            issues.add(
                f"interaction {interaction_id} result=unknown requires an unresolved interaction record"
            )

    # Validate unresolved references and source-scoped semantics.
    type_indexes: dict[str, dict[str, dict[str, Any]]] = {
        "surface": surfaces,
        "node": nodes,
        "state": states,
        "interaction": interactions,
    }
    for unresolved_id, item in unresolved.items():
        scope_type = item["scopeType"]
        scope_id = item["scopeId"]
        if scope_type == "source":
            if scope_id is not None:
                issues.add(
                    f"unresolved {unresolved_id} with scopeType=source must use scopeId=null"
                )
            continue
        if scope_id is None:
            issues.add(
                f"unresolved {unresolved_id} with scopeType={scope_type} requires scopeId"
            )
            continue
        if scope_id not in type_indexes[scope_type]:
            issues.add(
                f"unresolved {unresolved_id} references missing {scope_type} {scope_id}"
            )

    # Certification forbids known uncertainty and unknown interaction outcomes.
    if certify:
        uninspected = sorted(
            record["path"] for record in file_records if not record["inspected"]
        )
        if uninspected:
            issues.add(
                "certification forbids uninspected source files: "
                + ", ".join(uninspected)
            )
        if unresolved:
            issues.add(
                f"certification requires unresolved=[]; found {len(unresolved)} item(s)"
            )
        unknown = sorted(
            interaction_id
            for interaction_id, interaction in interactions.items()
            if interaction["result"] == "unknown"
        )
        if unknown:
            issues.add(
                "certification forbids interactions with result=unknown: "
                + ", ".join(unknown)
            )

    return issues


def validate_review_invariants(
    data: dict[str, Any],
    pass_number: int | None,
    decomposition: dict[str, Any] | None,
    decomposition_path: Path | None,
    request_path: Path | None,
) -> Issues:
    """Validate review outcome, artifact binding, and exhaustive per-surface audit coverage."""

    issues = Issues()

    if pass_number is not None and data["reviewPass"] != pass_number:
        issues.add(
            f"reviewPass mismatch: expected {pass_number}, found {data['reviewPass']}"
        )

    if decomposition_path is not None:
        expected = sha256_file(decomposition_path)
        actual = data["reviewedArtifacts"]["decompositionSha256"]
        if actual != expected:
            issues.add(
                f"review decomposition digest mismatch: expected {expected}, found {actual}"
            )

    if request_path is not None:
        expected = sha256_file(request_path)
        actual = data["reviewedArtifacts"]["requestSha256"]
        if actual != expected:
            issues.add(
                f"review request digest mismatch: expected {expected}, found {actual}"
            )

    finding_ids: set[str] = set()
    for finding in data["findings"]:
        finding_id = finding["id"]
        if finding_id in finding_ids:
            issues.add(f"duplicate finding id: {finding_id}")
        finding_ids.add(finding_id)

    if data["changeRequested"]:
        if data["certification"] != "incomplete":
            issues.add("changeRequested=true requires certification='incomplete'")
        if not data["findings"]:
            issues.add("changeRequested=true requires at least one finding")
    else:
        if data["certification"] != "complete":
            issues.add("changeRequested=false requires certification='complete'")
        if data["findings"]:
            issues.add("changeRequested=false requires findings=[]")

    if decomposition is None:
        return issues

    if data["reviewedArtifacts"]["requestSha256"] != decomposition["requestSha256"]:
        issues.add(
            "review request digest does not match the request digest embedded in decomposition"
        )

    surfaces = {item["id"]: item for item in decomposition["surfaces"]}
    nodes = {item["id"]: item for item in decomposition["nodes"]}
    states = {item["id"]: item for item in decomposition["states"]}
    interactions = {item["id"]: item for item in decomposition["interactions"]}
    unresolved = {item["id"]: item for item in decomposition["unresolved"]}
    global_ids = (
        set(surfaces) | set(nodes) | set(states) | set(interactions) | set(unresolved)
    )

    # Reviewer must inspect every source file the decomposition claims to depend on.
    required_files = {record["path"] for record in decomposition["source"]["filesRead"]}
    inspected_files = set(data["sourceFilesInspected"])
    missing_files = sorted(required_files - inspected_files)
    if missing_files:
        issues.add(
            "review sourceFilesInspected missing decomposition source files: "
            + ", ".join(missing_files)
        )

    # Each decomposition surface and every entity on it must have one independent source audit.
    audit_keys: set[str] = set()
    matched_surfaces: dict[str, dict[str, Any]] = {}
    unmatched_observations = 0

    def validate_entity_audits(
        *,
        surface_audit_key: str,
        entity_label: str,
        audits: list[dict[str, Any]],
        expected_ids: set[str],
    ) -> int:
        """Require exactly one matched independent audit per decomposition entity."""

        local_unmatched = 0
        matched_ids: set[str] = set()
        local_keys: set[str] = set()
        for entity_audit in audits:
            key = entity_audit["auditKey"]
            if key in audit_keys or key in local_keys:
                issues.add(f"duplicate audit key: {key}")
            local_keys.add(key)
            audit_keys.add(key)

            matched_id = entity_audit["matchedId"]
            if matched_id is None:
                local_unmatched += 1
                continue
            if matched_id not in expected_ids:
                issues.add(
                    f"{surface_audit_key} {entity_label} audit {key} matches id {matched_id} "
                    "that does not belong to this surface/entity type"
                )
                continue
            if matched_id in matched_ids:
                issues.add(
                    f"{surface_audit_key} {entity_label} {matched_id} is matched by more than one audit"
                )
            matched_ids.add(matched_id)

        missing = sorted(expected_ids - matched_ids)
        if missing:
            issues.add(
                f"{surface_audit_key} did not independently audit {entity_label} ids: "
                + ", ".join(missing)
            )
        return local_unmatched

    for audit in data["surfaceAudits"]:
        audit_key = audit["auditKey"]
        if audit_key in audit_keys:
            issues.add(f"duplicate audit key: {audit_key}")
        audit_keys.add(audit_key)

        surface_id = audit["matchedSurfaceId"]
        if surface_id is None:
            unmatched_observations += 1
            for entity_label, entity_audits in (
                ("node", audit["nodeAudits"]),
                ("state", audit["stateAudits"]),
                ("interaction", audit["interactionAudits"]),
            ):
                for entity_audit in entity_audits:
                    key = entity_audit["auditKey"]
                    if key in audit_keys:
                        issues.add(f"duplicate audit key: {key}")
                    audit_keys.add(key)
                    if entity_audit["matchedId"] is not None:
                        issues.add(
                            f"unmatched surface audit {audit_key} has {entity_label} audit {key} "
                            "matched to decomposition content"
                        )
                    unmatched_observations += 1
            continue

        if surface_id not in surfaces:
            issues.add(
                f"surface audit {audit_key} references missing matchedSurfaceId {surface_id}"
            )
            continue
        if surface_id in matched_surfaces:
            issues.add(
                f"surface {surface_id} is matched by more than one surface audit"
            )
            continue
        matched_surfaces[surface_id] = audit

        node_ids, state_ids, interaction_ids = surface_entity_sets(
            surface_id, nodes, states, interactions
        )
        unmatched_observations += validate_entity_audits(
            surface_audit_key=audit_key,
            entity_label="node",
            audits=audit["nodeAudits"],
            expected_ids=node_ids,
        )
        unmatched_observations += validate_entity_audits(
            surface_audit_key=audit_key,
            entity_label="state",
            audits=audit["stateAudits"],
            expected_ids=state_ids,
        )
        unmatched_observations += validate_entity_audits(
            surface_audit_key=audit_key,
            entity_label="interaction",
            audits=audit["interactionAudits"],
            expected_ids=interaction_ids,
        )

    missing_surface_audits = sorted(set(surfaces) - set(matched_surfaces))
    if missing_surface_audits:
        issues.add(
            "review did not independently audit decomposition surfaces: "
            + ", ".join(missing_surface_audits)
        )

    # A passing review cannot contain independently observed unmatched content at any level.
    if not data["changeRequested"] and unmatched_observations:
        issues.add(
            "passing review cannot contain unmatched independently observed surfaces/entities"
        )

    # Findings may only point at real decomposition entities; missing entities use affectedIds=[].
    for finding in data["findings"]:
        for affected_id in finding["affectedIds"]:
            if affected_id not in global_ids:
                issues.add(
                    f"finding {finding['id']} affectedIds references unknown id {affected_id}"
                )
        for change in finding["requiredChanges"]:
            target_id = change["targetId"]
            if target_id is not None and target_id not in global_ids:
                issues.add(
                    f"finding {finding['id']} change targetId references unknown id {target_id}"
                )
            if (
                change["operation"]
                in {
                    "update",
                    "remove",
                    "split-node",
                    "merge-nodes",
                    "reparent",
                    "resolve-unresolved",
                }
                and target_id is None
            ):
                issues.add(
                    f"finding {finding['id']} operation={change['operation']} requires targetId"
                )
            if (
                change["operation"] == "resolve-unresolved"
                and target_id is not None
                and target_id not in unresolved
            ):
                issues.add(
                    f"finding {finding['id']} resolve-unresolved target {target_id} is not unresolved"
                )

    return issues


def validate_correction_invariants(
    data: dict[str, Any],
    review: dict[str, Any],
    before_path: Path,
    after_path: Path,
    after: dict[str, Any],
) -> Issues:
    """Validate that every adversarial finding received an explicit correction disposition."""

    issues = Issues()
    before_digest = sha256_file(before_path)
    after_digest = sha256_file(after_path)

    if data["reviewPass"] != review["reviewPass"]:
        issues.add(
            f"correction reviewPass mismatch: expected {review['reviewPass']}, found {data['reviewPass']}"
        )
    if not review["changeRequested"]:
        issues.add("correction report requires a review with changeRequested=true")
    if data["baseDecompositionSha256"] != before_digest:
        issues.add("correction baseDecompositionSha256 does not match --before")
    if data["resultDecompositionSha256"] != after_digest:
        issues.add("correction resultDecompositionSha256 does not match --after")
    if review["reviewedArtifacts"]["decompositionSha256"] != before_digest:
        issues.add(
            "correction --before is not the decomposition reviewed by the supplied review"
        )
    before = load_json(before_path)
    if before["requestSha256"] != after["requestSha256"]:
        issues.add("correction changed requestSha256")
    if review["reviewedArtifacts"]["requestSha256"] != after["requestSha256"]:
        issues.add(
            "corrected decomposition requestSha256 does not match reviewed request"
        )

    expected_findings = {finding["id"] for finding in review["findings"]}
    seen_findings: set[str] = set()
    applied = False
    for resolution in data["resolutions"]:
        finding_id = resolution["findingId"]
        if finding_id in seen_findings:
            issues.add(f"duplicate correction resolution for finding {finding_id}")
        seen_findings.add(finding_id)
        if finding_id not in expected_findings:
            issues.add(f"correction resolves unknown finding {finding_id}")
        if resolution["disposition"] == "applied":
            applied = True

    missing = sorted(expected_findings - seen_findings)
    if missing:
        issues.add(
            "correction report missing finding resolutions: " + ", ".join(missing)
        )
    extra = sorted(seen_findings - expected_findings)
    if extra:
        issues.add(
            "correction report contains extra finding resolutions: " + ", ".join(extra)
        )
    if applied and before_digest == after_digest:
        issues.add(
            "at least one finding is marked applied but decomposition digest did not change"
        )

    # The corrected artifact must itself be structurally certifiable before the next review.
    issues.extend(validate_decomposition_invariants(after, certify=True).items)
    return issues


def print_result(
    kind: str, path: Path, data: dict[str, Any], issues: Issues, certify: bool = False
) -> None:
    """Print a compact, deterministic validation report."""

    if issues:
        print(f"FAIL {kind}: {path}", file=sys.stderr)
        for issue in issues.items:
            print(f"- {issue}", file=sys.stderr)
        return

    if kind == "decomposition":
        print(
            "PASS decomposition: "
            f"surfaces={len(data['surfaces'])} "
            f"nodes={len(data['nodes'])} "
            f"states={len(data['states'])} "
            f"interactions={len(data['interactions'])} "
            f"unresolved={len(data['unresolved'])} "
            f"certified={'yes' if certify else 'not-requested'}"
        )
    elif kind == "review":
        print(
            "PASS review: "
            f"pass={data['reviewPass']} "
            f"changeRequested={str(data['changeRequested']).lower()} "
            f"surfaceAudits={len(data['surfaceAudits'])} "
            f"findings={len(data['findings'])} "
            f"certification={data['certification']}"
        )
    else:
        print(
            "PASS correction: "
            f"reviewPass={data['reviewPass']} "
            f"resolutions={len(data['resolutions'])}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="kind", required=True)

    decomposition = subparsers.add_parser(
        "decomposition", help="Validate a UI decomposition"
    )
    decomposition.add_argument("path", type=Path)
    decomposition.add_argument(
        "--certify",
        action="store_true",
        help="Also require zero unresolved items and no unknown interaction results",
    )
    decomposition.add_argument(
        "--request",
        type=Path,
        help="Bind the decomposition to the exact request.txt bytes",
    )

    review = subparsers.add_parser("review", help="Validate an adversarial review")
    review.add_argument("path", type=Path)
    review.add_argument("--pass-number", type=int, choices=(1, 2, 3))
    review.add_argument("--decomposition", type=Path)
    review.add_argument("--request", type=Path)

    correction = subparsers.add_parser(
        "correction", help="Validate a correction report"
    )
    correction.add_argument("path", type=Path)
    correction.add_argument("--review", type=Path, required=True)
    correction.add_argument("--before", type=Path, required=True)
    correction.add_argument("--after", type=Path, required=True)

    return parser


def main() -> int:
    """Validate the requested artifact and return a shell-friendly exit code."""

    args = build_parser().parse_args()

    try:
        data = load_json(args.path)
    except ValueError as exc:
        print(f"FAIL {args.kind}: {exc}", file=sys.stderr)
        return 1

    issues = Issues()

    try:
        if args.kind == "decomposition":
            issues.extend(
                schema_issues(data, SCHEMA_DIR / "ui-decomposition.schema.json")
            )
            if not issues:
                issues.extend(
                    validate_decomposition_invariants(
                        data, args.certify, args.request
                    ).items
                )
            print_result("decomposition", args.path, data, issues, certify=args.certify)

        elif args.kind == "review":
            issues.extend(
                schema_issues(data, SCHEMA_DIR / "adversarial-review.schema.json")
            )
            decomposition_data: dict[str, Any] | None = None
            if args.decomposition is not None:
                decomposition_data = load_json(args.decomposition)
                decomposition_schema_errors = schema_issues(
                    decomposition_data, SCHEMA_DIR / "ui-decomposition.schema.json"
                )
                issues.extend(
                    f"reviewed decomposition invalid: {message}"
                    for message in decomposition_schema_errors
                )
            if not issues:
                issues.extend(
                    validate_review_invariants(
                        data,
                        args.pass_number,
                        decomposition_data,
                        args.decomposition,
                        args.request,
                    ).items
                )
            print_result("review", args.path, data, issues)

        else:
            issues.extend(
                schema_issues(data, SCHEMA_DIR / "correction-report.schema.json")
            )
            review_data = load_json(args.review)
            before_data = load_json(args.before)
            after_data = load_json(args.after)
            issues.extend(
                schema_issues(
                    review_data, SCHEMA_DIR / "adversarial-review.schema.json"
                )
            )
            issues.extend(
                schema_issues(before_data, SCHEMA_DIR / "ui-decomposition.schema.json")
            )
            issues.extend(
                schema_issues(after_data, SCHEMA_DIR / "ui-decomposition.schema.json")
            )
            if not issues:
                issues.extend(
                    validate_correction_invariants(
                        data, review_data, args.before, args.after, after_data
                    ).items
                )
            print_result("correction", args.path, data, issues)

    except ValueError as exc:
        print(f"FAIL {args.kind}: {exc}", file=sys.stderr)
        return 1

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
