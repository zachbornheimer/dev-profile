#!/usr/bin/env python3
"""Render a master agent definition into a harness's own artifact.

Master:  ~/.agents/agents/<name>.yaml   (schema: agents/v1 — see README.md)
Targets: omp -> ~/.omp/agent/agents/<name>.md

Every render is deterministic and idempotent: an unchanged artifact is not
rewritten, and every artifact names the master it came from, so nobody edits
the rendered file by hand. A capability the harness cannot express is reported
on stderr rather than approximated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

MASTERS = Path(__file__).resolve().parent
SCHEMA = "agents/v1"

# Canonical capability -> the tool omp mounts for it. None means omp has no
# equivalent; the renderer reports it and the prompt's search rule still holds.
OMP_TOOLS: dict[str, str | None] = {
    "read": "read",
    "write": "write",
    "edit": "edit",
    "glob": "glob",
    "grep": "grep",
    "list": "find",
    "stat": None,  # omp has no metadata tool; glob answers most of it
    "run_command": "bash",
    "run_tests": "bash",
    "worktrunk": "bash",
    "web_search": "web_search",
    "web_fetch": None,  # omp fetches a URL through read when its toolset allows it
    "search_tools": None,  # omp has no tool search; its tools are inline
    "collect_failure_evidence": None,
    "atask_list": None,
    "atask_show": None,
    "atask_file": None,
    "atask_claim": None,
    "atask_log": None,
    "atask_verify_complete": None,
    "hindsight_recall": None,
    "hindsight_retain": None,
}

MODEL_ROLES = {"default", "smol", "slow", "plan", "task"}
THINKING = {"auto", "low", "medium", "high"}


def load(name: str) -> dict:
    path = MASTERS / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"no master definition: {path}")
    doc = yaml.safe_load(path.read_text())
    if doc.get("schema") != SCHEMA:
        raise SystemExit(f"{path}: schema must be {SCHEMA}, got {doc.get('schema')!r}")
    if doc.get("name") != name:
        raise SystemExit(f"{path}: name must match the file name ({name}), got {doc.get('name')!r}")
    role = (doc.get("model") or {}).get("role", "default")
    if role not in MODEL_ROLES:
        raise SystemExit(f"{path}: model.role must be one of {sorted(MODEL_ROLES)}, got {role!r}")
    thinking = (doc.get("model") or {}).get("thinkingLevel")
    if thinking is not None and thinking not in THINKING:
        raise SystemExit(f"{path}: model.thinkingLevel must be one of {sorted(THINKING)}, got {thinking!r}")
    return doc


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def bindings(doc: dict) -> tuple[list[str], list[str]]:
    """The omp tool list, and the canonical capabilities omp cannot express."""
    tools: list[str] = []
    missing: list[str] = []
    for capability in list(doc.get("tools", {}).get("always", [])) + list(
        doc.get("tools", {}).get("searchable", [])
    ):
        target = OMP_TOOLS.get(capability)
        if target is None:
            missing.append(capability)
        elif target not in tools:
            tools.append(target)
    return tools, missing


def render_omp(doc: dict) -> str:
    all_tools = bool((doc.get("tools") or {}).get("all"))
    tools, missing = bindings(doc)
    harness = (doc.get("harnesses") or {}).get("omp") or {}
    name = harness.get("name", doc["name"])

    front: dict = {"name": name, "description": one_line(doc["description"])}
    # No `tools:` key means every tool omp mounts; that is the `tools.all` request.
    if tools and not all_tools:
        front["tools"] = tools
    if doc.get("tools", {}).get("denied"):
        raise SystemExit("omp cannot deny a tool by name; express the constraint in the prompt instead")
    if doc.get("spawns") == "*":
        front["spawns"] = "*"
    elif doc.get("spawns"):
        front["spawns"] = list(doc["spawns"])
    role = (doc.get("model") or {}).get("role", "default")
    model = harness.get("model") or ([f"@{role}"] if role != "default" else [])
    if model:
        front["model"] = model
    thinking = (doc.get("model") or {}).get("thinkingLevel")
    if thinking:
        front["thinkingLevel"] = thinking
    if (doc.get("output") or "none") != "none":
        raise SystemExit("structured output is not rendered for omp yet; add it to the renderer first")

    if not all_tools:
        for capability in missing:
            print(f"omp has no tool for {capability}; it is left out of the tool list", file=sys.stderr)

    header = (
        f"<!-- generated from ~/.agents/agents/{doc['name']}.yaml by render.py — do not edit -->\n\n"
    )
    body = doc["prompt"].rstrip() + "\n"
    return f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n\n{header}{body}"


def target_for(doc: dict, harness: str) -> Path:
    if harness != "omp":
        raise SystemExit(f"unknown harness: {harness}")
    name = ((doc.get("harnesses") or {}).get("omp") or {}).get("name", doc["name"])
    return Path.home() / ".omp" / "agent" / "agents" / f"{name}.md"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Render master agent definitions.")
    parser.add_argument("name", help="master name, without .yaml")
    parser.add_argument("--harness", default="omp", help="target harness (default: omp)")
    parser.add_argument("--check", action="store_true", help="exit 1 when the artifact is stale")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = parser.parse_args(argv)

    doc = load(args.name)
    rendered = render_omp(doc) if args.harness == "omp" else None
    if rendered is None:
        raise SystemExit(f"unknown harness: {args.harness}")

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    path = target_for(doc, args.harness)
    current = path.read_text() if path.exists() else ""
    if current == rendered:
        print(f"{path}: up to date")
        return 0
    if args.check:
        print(f"{path}: stale (run render.py {args.name})", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    print(f"{path}: written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
