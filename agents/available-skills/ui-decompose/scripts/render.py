#!/usr/bin/env python3
"""Render a validated UI decomposition to exhaustive Markdown."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON artifact."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def md(value: Any) -> str:
    """Escape a scalar for a Markdown table cell."""

    if value is None:
        return "—"
    text = str(value).replace("|", "\\|").replace("\n", "<br>")
    return text if text else "—"


def join(values: list[str]) -> str:
    """Join values for compact table display."""

    return md(", ".join(values)) if values else "—"


def evidence_text(evidence: list[dict[str, Any]]) -> str:
    """Render evidence records with kind and locator."""

    chunks: list[str] = []
    for item in evidence:
        chunk = f"[{item['kind']}] {item['source']} @ {item['locator']}"
        if item.get("note"):
            chunk += f" — {item['note']}"
        chunks.append(chunk)
    return md("; ".join(chunks))


def build_tree(root_id: str, nodes: dict[str, dict[str, Any]]) -> list[str]:
    """Render a deterministic Unicode component tree."""

    lines: list[str] = []

    def label(node_id: str) -> str:
        node = nodes[node_id]
        return f"{node['name']} ({node_id}){' [atomic]' if node['atomic'] else ''}"

    def visit(node_id: str, prefix: str, is_last: bool) -> None:
        lines.append(prefix + ("└── " if is_last else "├── ") + label(node_id))
        children = nodes[node_id]["childIds"]
        child_prefix = prefix + ("    " if is_last else "│   ")
        for index, child_id in enumerate(children):
            visit(child_id, child_prefix, index == len(children) - 1)

    lines.append(label(root_id))
    children = nodes[root_id]["childIds"]
    for index, child_id in enumerate(children):
        visit(child_id, "", index == len(children) - 1)
    return lines


def surface_nodes(surface_id: str, nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return nodes on a surface in source JSON order."""

    return [node for node in nodes.values() if node["surfaceId"] == surface_id]


def surface_states(
    surface_id: str,
    nodes: dict[str, dict[str, Any]],
    states: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return surface-owned and node-owned states for a surface."""

    node_ids = {node["id"] for node in surface_nodes(surface_id, nodes)}
    return [
        state
        for state in states
        if (state["ownerType"] == "surface" and state["ownerId"] == surface_id)
        or (state["ownerType"] == "node" and state["ownerId"] in node_ids)
    ]


def surface_interactions(
    surface_id: str,
    nodes: dict[str, dict[str, Any]],
    interactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return interactions originating from nodes on a surface."""

    node_ids = {node["id"] for node in surface_nodes(surface_id, nodes)}
    return [interaction for interaction in interactions if interaction["sourceNodeId"] in node_ids]


def unresolved_for_surface(
    surface_id: str,
    nodes: dict[str, dict[str, Any]],
    states: dict[str, dict[str, Any]],
    interactions: dict[str, dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return unresolved items that belong to a surface or descendants."""

    node_ids = {node["id"] for node in surface_nodes(surface_id, nodes)}
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
    ids_by_type = {
        "surface": {surface_id},
        "node": node_ids,
        "state": state_ids,
        "interaction": interaction_ids,
    }
    return [
        item
        for item in unresolved
        if item["scopeType"] != "source"
        and item["scopeId"] in ids_by_type[item["scopeType"]]
    ]


def render(data: dict[str, Any], review: dict[str, Any] | None = None) -> str:
    """Build the complete Markdown report."""

    surfaces = data["surfaces"]
    nodes = {node["id"]: node for node in data["nodes"]}
    states = {state["id"]: state for state in data["states"]}
    interactions = {interaction["id"]: interaction for interaction in data["interactions"]}
    unresolved = data["unresolved"]

    lines: list[str] = [
        f"# {data['title']}",
        "",
        "Generated from the schema-validated UI decomposition. This describes the design as observed; it does not prescribe a UI kit or implementation strategy.",
        "",
        "## Scope",
        "",
        f"- Requested: {md(data['scope']['requested'])}",
        f"- Root surfaces: {join([f'`{value}`' for value in data['scope']['rootSurfaceIds']])}",
    ]

    if data["scope"]["exclusions"]:
        lines.extend(["", "### Explicit exclusions", ""])
        for exclusion in data["scope"]["exclusions"]:
            evidence = evidence_text(exclusion.get("evidence", [])) if exclusion.get("evidence") else "—"
            lines.append(
                f"- **{exclusion['description']}** — {exclusion['reason']}. Evidence: {evidence}"
            )
    else:
        lines.extend(["", "Explicit exclusions: none."])

    lines.extend(["", "## Source", "", f"- Type: `{data['source']['type']}`"])
    if data["source"].get("project"):
        lines.append(f"- Project: {data['source']['project']}")
    lines.append(
        f"- Entry files: {', '.join(f'`{entry}`' for entry in data['source']['entryFiles'])}"
    )
    lines.extend(
        [
            "",
            "### Inspected source files",
            "",
            "| File | Role | Notes |",
            "| --- | --- | --- |",
        ]
    )
    for record in data["source"]["filesRead"]:
        lines.append(
            f"| {md(record['path'])} | {md(record['role'])} | {join(record.get('notes', []))} |"
        )

    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Surfaces: **{len(surfaces)}**",
            f"- Component instances: **{len(nodes)}**",
            f"- States: **{len(states)}**",
            f"- Interactions: **{len(interactions)}**",
            f"- Unresolved: **{len(unresolved)}**",
            "",
            "| # | Surface | Type | Components | States | Interactions | Unresolved |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for index, surface in enumerate(surfaces, start=1):
        node_count = len(surface_nodes(surface["id"], nodes))
        state_count = len(surface_states(surface["id"], nodes, list(states.values())))
        interaction_count = len(
            surface_interactions(surface["id"], nodes, list(interactions.values()))
        )
        unresolved_count = len(
            unresolved_for_surface(surface["id"], nodes, states, interactions, unresolved)
        )
        lines.append(
            f"| {index} | {md(surface['name'])} (`{surface['id']}`) | {md(surface['type'])} | {node_count} | {state_count} | {interaction_count} | {unresolved_count} |"
        )

    lines.extend(["", "## Surface index", ""])
    for index, surface in enumerate(surfaces, start=1):
        lines.append(f"{index}. **{surface['name']}** — `{surface['id']}` ({surface['type']})")

    lines.extend(["", "## Surface decompositions", ""])

    for index, surface in enumerate(surfaces, start=1):
        sid = surface["id"]
        s_nodes = surface_nodes(sid, nodes)
        s_states = surface_states(sid, nodes, list(states.values()))
        s_interactions = surface_interactions(sid, nodes, list(interactions.values()))
        s_unresolved = unresolved_for_surface(sid, nodes, states, interactions, unresolved)
        parent = f"`{surface['parentSurfaceId']}`" if surface["parentSurfaceId"] else "—"

        lines.extend(
            [
                f"### {index}. {surface['name']}",
                "",
                f"- ID: `{sid}`",
                f"- Type: `{surface['type']}`",
                f"- Parent surface: {parent}",
                f"- Root component: `{surface['rootNodeId']}`",
                f"- Trigger interactions: {join([f'`{value}`' for value in surface['triggerInteractionIds']])}",
                f"- Evidence: {evidence_text(surface['evidence'])}",
            ]
        )
        if surface.get("notes"):
            lines.append(f"- Notes: {join(surface['notes'])}")

        lines.extend(["", "#### Component hierarchy", "", "```text"])
        lines.extend(build_tree(surface["rootNodeId"], nodes))
        lines.extend(["```", "", "#### Component instances", ""])
        lines.extend(
            [
                "| Component | Parent | Role | Kind | Atomic | Interactive | Visible text | States | Interactions | Evidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for node in s_nodes:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{md(node['name'])} (`{node['id']}`)",
                        f"`{node['parentId']}`" if node["parentId"] else "—",
                        md(node["role"]),
                        md(node["kind"]),
                        "Yes" if node["atomic"] else "No",
                        "Yes" if node["interactive"] else "No",
                        join(node["visibleText"]),
                        join([f"`{value}`" for value in node["stateIds"]]),
                        join([f"`{value}`" for value in node["interactionIds"]]),
                        evidence_text(node["evidence"]),
                    ]
                )
                + " |"
            )

        lines.extend(["", "#### States", ""])
        if s_states:
            lines.extend(
                [
                    "| State | Owner | Kind | Trigger | Changes | Evidence |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for state in s_states:
                lines.append(
                    f"| {md(state['name'])} (`{state['id']}`) | {state['ownerType']} `{state['ownerId']}` | {md(state['kind'])} | {md(state.get('trigger'))} | {join(state['changes'])} | {evidence_text(state['evidence'])} |"
                )
        else:
            lines.append("No states documented.")

        lines.extend(["", "#### Interactions", ""])
        if s_interactions:
            lines.extend(
                [
                    "| Interaction | Source | Gesture | Result | Target surface | Target state | Description | Evidence |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for interaction in s_interactions:
                target_surface = (
                    f"`{interaction['targetSurfaceId']}`" if interaction["targetSurfaceId"] else "—"
                )
                target_state = (
                    f"`{interaction['targetStateId']}`" if interaction["targetStateId"] else "—"
                )
                lines.append(
                    f"| {md(interaction['name'])} (`{interaction['id']}`) | `{interaction['sourceNodeId']}` | {md(interaction['gesture'])} | {md(interaction['result'])} | {target_surface} | {target_state} | {md(interaction['description'])} | {evidence_text(interaction['evidence'])} |"
                )
        else:
            lines.append("No interactions originate on this surface.")

        lines.extend(["", "#### Unresolved", ""])
        if s_unresolved:
            for item in s_unresolved:
                lines.append(
                    f"- `{item['id']}` — **{item['question']}** Scope: {item['scopeType']} `{item['scopeId']}`. Reason: {item['reason']}. Evidence: {evidence_text(item['evidence'])}"
                )
        else:
            lines.append("None.")
        lines.append("")

    source_unresolved = [item for item in unresolved if item["scopeType"] == "source"]
    lines.extend(["## Source-level unresolved items", ""])
    if source_unresolved:
        for item in source_unresolved:
            lines.append(
                f"- `{item['id']}` — **{item['question']}** Reason: {item['reason']}. Evidence: {evidence_text(item['evidence'])}"
            )
    else:
        lines.append("None.")

    if review is not None:
        lines.extend(
            [
                "",
                "## Certification",
                "",
                f"- Adversarial review pass: **{review['reviewPass']}**",
                f"- Certification: **{review['certification'].upper()}**",
                f"- Change requested: **{'Yes' if review['changeRequested'] else 'No'}**",
                f"- Independently audited surfaces: **{len(review['surfaceAudits'])}**",
                f"- Findings: **{len(review['findings'])}**",
                f"- Reviewed decomposition SHA-256: `{review['reviewedArtifacts']['decompositionSha256']}`",
                "",
                review["summary"],
            ]
        )

    if data.get("notes"):
        lines.extend(["", "## Notes", ""])
        for note in data["notes"]:
            lines.append(f"- {note}")

    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Validated ui-decomposition.json")
    parser.add_argument("output", type=Path, help="Markdown output path")
    parser.add_argument("--review", type=Path, help="Passing adversarial review to render")
    return parser


def main() -> int:
    """Render the input JSON to the requested Markdown path."""

    args = build_parser().parse_args()
    data = load_json(args.input)
    review = load_json(args.review) if args.review else None
    output = render(data, review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Rendered {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
