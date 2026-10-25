#!/usr/bin/env -S uv run --script
"""Harvest repeated Gas City role/formula/skill signals as NDJSON.

This is evidence collection only. It never edits transcripts, city files, or
Beads. Clustering, skepticism, and bead creation belong to the skill workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SIGNALS = {
    "role": re.compile(r"\b(?:role|agent|reviewer|planner|worker|triager|publisher|operator|decomposer|analyst|synthesizer)\b", re.I),
    "formula": re.compile(r"\b(?:formula|workflow|pipeline|gc sling|drain|convoy|fanout|stage)\b", re.I),
    "skill": re.compile(r"(?:available-skills|SKILL\.md|load .*skill|/[-a-z]+)\b", re.I),
    "routing": re.compile(r"\b(?:route|dispatch|sling|handoff|wrong agent|should go to|needs a lane)\b", re.I),
    "guard": re.compile(r"\b(?:must verify|not proven|red test|gate|never auto|do not close|blocked)\b", re.I),
}
REPEATED = re.compile(r"\b(?:again|repeated|every time|keep(?:s)?|missing|should have|we need|add a|create a)\b", re.I)
MAX_TEXT = 1_200


def _jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def _text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(_text(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    return ""


def _record(kind: str, text: str, tool: str, session: str, repo: str, stamp: str, source: Path):
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) < 24:
        return None
    return {
        "kind": kind,
        "text": normalized[:MAX_TEXT],
        "tool": tool,
        "session": session,
        "repo_or_project": repo or "unknown",
        "approx_date": stamp[:10] or "unknown",
        "source": str(source),
        "fingerprint": hashlib.sha256(normalized.encode()).hexdigest()[:16],
    }


def _signals(text: str):
    if not REPEATED.search(text):
        return []
    return [name for name, pattern in SIGNALS.items() if pattern.search(text)]


def harvest_claude(cutoff: datetime):
    root = Path.home() / ".claude" / "projects"
    if not root.is_dir():
        return
    for source in root.rglob("*.jsonl"):
        if datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc) < cutoff:
            continue
        for item in _jsonl(source):
            if item.get("type") not in {"user", "assistant"}:
                continue
            message = item.get("message") or {}
            text = _text(message.get("content", "")) if isinstance(message, dict) else ""
            for kind in _signals(text):
                result = _record(kind, text, "claude-code", source.stem, source.parent.name, item.get("timestamp", ""), source)
                if result:
                    yield result


def harvest_codex(cutoff: datetime):
    root = Path.home() / ".codex" / "sessions"
    if not root.is_dir():
        return
    for source in root.rglob("*.jsonl"):
        if datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc) < cutoff:
            continue
        repo = ""
        for item in _jsonl(source):
            if item.get("type") == "session_meta":
                repo = (item.get("payload") or {}).get("cwd", "")
                continue
            if item.get("type") != "response_item":
                continue
            payload = item.get("payload") or {}
            if payload.get("role") not in {"user", "assistant"}:
                continue
            text = _text(payload.get("content", []))
            for kind in _signals(text):
                result = _record(kind, text, "codex", source.stem, repo, item.get("timestamp", ""), source)
                if result:
                    yield result


def inventory(city: Path):
    role_paths = list((city / "agents").glob("gc.*")) + list((city / "agents").glob("gc-*"))
    seen = set()
    for path in sorted(role_paths):
        if path in seen:
            continue
        seen.add(path)
        name = path.name.removeprefix("gc.").removeprefix("gc-")
        yield {"kind": "existing-role", "name": name, "path": str(path)}
    for path in sorted((city / "formulas").glob("*.formula.toml")):
        yield {"kind": "existing-formula", "name": path.stem.removesuffix(".formula"), "path": str(path)}
    for path in sorted((Path.home() / ".agents" / "available-skills").glob("*/SKILL.md")):
        yield {"kind": "existing-skill", "name": path.parent.name, "path": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=Path, required=True)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=args.days)
    observations: dict[str, dict] = {}
    count = 0
    for row in [*harvest_claude(cutoff), *harvest_codex(cutoff)]:
        key = row["fingerprint"]
        if key in observations:
            kind = row.pop("kind")
            if kind not in observations[key].setdefault("kinds", []):
                observations[key]["kinds"].append(kind)
        else:
            row["kinds"] = [row.pop("kind")]
            observations[key] = row
    for row in observations.values():
        print(json.dumps(row, ensure_ascii=False))
        count += 1
    for row in inventory(args.city):
        print(json.dumps(row, ensure_ascii=False))
    print(f"harvested {count} candidate observations", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
