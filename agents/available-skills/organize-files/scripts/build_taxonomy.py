#!/usr/bin/env python3
"""Build `taxonomy.json` from the repo catalog, Linear projects, personal
areas and overrides. Pure and deterministic: the only non-determinism in the
output is `generated_at`. See /tmp/organize/taxonomy-design.md section 1 for
the schema and section 1.3 for the derivation rules (P0-P7), implemented in
taxonomy_rules.py.

Usage: python3 build_taxonomy.py [--data-dir DIR] [--developer-root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from taxonomy_devclone import discover_developer_clones
from taxonomy_rules import BuildInputs, build_nodes

SCHEMA_VERSION = 1
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DEVELOPER_ROOT = Path.home() / "Developer"
TAXONOMY_VERSION_HASH_CHARS = 12


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> tuple[Any, str]:
    """Read and parse a JSON input file, returning (parsed, sha256-of-raw-bytes)."""
    raw = path.read_bytes()
    return json.loads(raw), _sha256_bytes(raw)


def _canonical_inputs_hash(inputs_by_name: dict[str, Any]) -> str:
    canonical = json.dumps(inputs_by_name, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canonical.encode("utf-8"))[:TAXONOMY_VERSION_HASH_CHARS]


def _clock_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_inputs(
    data_dir: Path, developer_root: Path
) -> tuple[BuildInputs, dict[str, Any]]:
    catalog, catalog_sha = _load_json(data_dir / "repo-catalog.json")
    linear, linear_sha = _load_json(data_dir / "linear-projects.json")
    personal, personal_sha = _load_json(data_dir / "personal-areas.json")
    overrides, overrides_sha = _load_json(data_dir / "taxonomy-overrides.json")

    inputs = BuildInputs(
        repos=catalog["repos"],
        linear_projects=linear["projects"],
        personal_areas=personal["areas"],
        overrides=overrides,
        developer_clones=discover_developer_clones(str(developer_root)),
    )
    sources = {
        "catalog": {
            "path": "repo-catalog.json",
            "generated_at": catalog.get("generated_at"),
            "sha256": catalog_sha,
        },
        "linear": {"path": "linear-projects.json", "sha256": linear_sha},
        "personal": {"path": "personal-areas.json", "sha256": personal_sha},
        "overrides": {"path": "taxonomy-overrides.json", "sha256": overrides_sha},
    }
    inputs_by_name = {
        "catalog": catalog,
        "linear": linear,
        "personal": personal,
        "overrides": overrides,
    }
    return inputs, {
        "sources": sources,
        "version_hash": _canonical_inputs_hash(inputs_by_name),
    }


def build_taxonomy(data_dir: Path, developer_root: Path) -> dict[str, Any]:
    inputs, meta = load_inputs(data_dir, developer_root)
    nodes = build_nodes(inputs)
    nodes.sort(key=lambda n: (n["depth"], n["id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": f"{SCHEMA_VERSION}.{meta['version_hash']}",
        "generated_at": _clock_now(),
        "sources": meta["sources"],
        "nodes": nodes,
    }


def _stable_view(document: dict[str, Any]) -> dict[str, Any]:
    """The document with `generated_at` removed, for change detection."""
    view = dict(document)
    view.pop("generated_at", None)
    return view


def _print_node_diff(
    old_nodes: list[dict[str, Any]], new_nodes: list[dict[str, Any]]
) -> None:
    old_by_id = {n["id"]: n for n in old_nodes}
    new_by_id = {n["id"]: n for n in new_nodes}
    added = sorted(set(new_by_id) - set(old_by_id))
    removed = sorted(set(old_by_id) - set(new_by_id))
    moved = sorted(
        node_id
        for node_id in set(old_by_id) & set(new_by_id)
        if old_by_id[node_id].get("parent") != new_by_id[node_id].get("parent")
    )
    if added:
        print(
            f"  added ({len(added)}): {', '.join(added[:20])}"
            + (" ..." if len(added) > 20 else "")
        )
    if removed:
        print(
            f"  removed ({len(removed)}): {', '.join(removed[:20])}"
            + (" ..." if len(removed) > 20 else "")
        )
    if moved:
        print(
            f"  moved ({len(moved)}): {', '.join(moved[:20])}"
            + (" ..." if len(moved) > 20 else "")
        )
    if not (added or removed or moved):
        print("  (no node-level differences)")


def write_taxonomy(document: dict[str, Any], output_path: Path) -> bool:
    """Write `taxonomy.json` only if its content (excluding generated_at)
    changed; print a node-level diff against the previous file when one
    exists. Returns True if the file was written."""
    if output_path.exists():
        previous = json.loads(output_path.read_text())
        if _stable_view(previous) == _stable_view(document):
            print(f"{output_path}: unchanged, not rewriting")
            return False
        print(f"{output_path}: content changed —")
        _print_node_diff(previous.get("nodes", []), document["nodes"])
    else:
        print(f"{output_path}: creating")

    output_path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--developer-root", type=Path, default=DEFAULT_DEVELOPER_ROOT)
    args = parser.parse_args(argv)

    document = build_taxonomy(args.data_dir, args.developer_root)
    write_taxonomy(document, args.data_dir / "taxonomy.json")

    by_depth: dict[int, int] = {}
    for node in document["nodes"]:
        by_depth[node["depth"]] = by_depth.get(node["depth"], 0) + 1
    print(f"taxonomy_version={document['taxonomy_version']} nodes_by_depth={by_depth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
