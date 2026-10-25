#!/usr/bin/env python3
"""Convert a Mastra agent definition into an agents/v1 master.

Source:  <repo>/mastra/src/agents/<name>/<name>.yaml   (Description, Use when, Prompt)
Output:  ~/.agents/agents/<name>.yaml

The prompt is rewritten from Mastra's tool names to the canonical capability
names the master format uses (README.md), so the rendered agent never names
another harness's tool. Anything the alias table does not know is reported, not
silently kept.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

MASTERS = Path(__file__).resolve().parent

# Mastra (or Mastra-adjacent) tool name -> canonical capability.
ALIASES: dict[str, str] = {
    "mastra_workspace_read_file": "read",
    "mastra_workspace_edit_file": "edit",
    "mastra_workspace_write_file": "write",
    "mastra_workspace_list_files": "list",
    "mastra_workspace_grep": "grep",
    "mastra_workspace_file_stat": "stat",
    "mastra_workspace_mkdir": "mkdir",
    "agentmux_capability_": "",
}

# A tool name this importer cannot place: it stays in the prompt, and the run
# prints it so a human maps it rather than guessing.
UNKNOWN_TOOL = re.compile(r"\b(mastra_[a-z_]+|agentmux_[a-z_]+)\b")

ALWAYS = ["read", "write", "edit", "glob", "grep", "list", "stat"]
SEARCHABLE = [
    "run_command",
    "run_tests",
    "search_tools",
    "worktrunk",
    "atask_list",
    "atask_show",
    "atask_file",
    "atask_claim",
    "atask_log",
    "atask_verify_complete",
    "hindsight_recall",
    "hindsight_retain",
    "web_search",
    "web_fetch",
    "collect_failure_evidence",
]


def normalize(text: str) -> str:
    for old, new in ALIASES.items():
        text = text.replace(old, new)
    return text


def block(text: str, indent: str = "  ") -> str:
    """The prompt as a literal block; a single trailing newline round-trips through `|`."""
    lines = text.rstrip("\n").split("\n")
    return "\n".join(f"{indent}{line}" if line.strip() else "" for line in lines) + "\n"


def convert(source: Path, name: str, description: str | None, when: str | None, role: str) -> tuple[str, list[str]]:
    doc = yaml.safe_load(source.read_text())
    # Byte for byte: the Mastra definition's own test proves the loaded prompt matches this file.
    prompt = normalize(str(doc.get("Prompt", "")))
    if not prompt:
        raise SystemExit(f"{source}: no Prompt")
    desc = description or " ".join(str(doc.get("Description", "")).split())
    when_to_use = when or " ".join(str(doc.get("Use when", "")).split())
    if not desc:
        raise SystemExit(f"{source}: no Description and none supplied")
    if not when_to_use:
        raise SystemExit(f"{source}: no 'Use when' and none supplied")

    unknown = sorted(set(UNKNOWN_TOOL.findall(prompt)))

    head = {
        "schema": "agents/v1",
        "name": name,
        "description": desc,
        "whenToUse": when_to_use,
        "tags": ["mastra-import"],
        "model": {"role": role},
        "workspace": "machine",
        "tools": {"all": True, "always": ALWAYS, "searchable": SEARCHABLE, "denied": []},
        "spawns": [],
        "output": "none",
    }
    text = (
        f"# Converted from {source} by import_mastra.py.\n"
        f"{yaml.safe_dump(head, sort_keys=False)}"
        f"prompt: |\n{block(prompt)}\n"
    )
    return text, unknown


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="the Mastra agent YAML")
    parser.add_argument("--name", required=True, help="master name (file stem)")
    parser.add_argument("--description", help="override the mastra Description")
    parser.add_argument("--when", help="override the mastra 'Use when'")
    parser.add_argument("--role", default="task", help="model role (default: task)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing master")
    args = parser.parse_args(argv)

    if not args.source.exists():
        raise SystemExit(f"no such file: {args.source}")
    target = MASTERS / f"{args.name}.yaml"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} exists; pass --force to overwrite")

    text, unknown = convert(args.source, args.name, args.description, args.when, args.role)
    target.write_text(text)
    print(f"{target}: written")
    for tool in unknown:
        print(f"unmapped tool name in the prompt: {tool}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
