"""Skill roster observation from SKILL.md files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from constants import DESCRIPTION_CHARS, SELECTOR_GROUPS, SKILL_ROOTS

FRONTMATTER_MARK = "---"


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    path: str = ""
    load: tuple[str, ...] = ()
    load_paths: tuple[str, ...] = ()


def collapse_roster(skills: list[Skill]) -> list[Skill]:
    by_name = {skill.name: skill for skill in skills}
    hidden: set[str] = set()
    primaries: dict[str, Skill] = {}
    for primary, hide, extras in SELECTOR_GROUPS:
        if primary not in by_name:
            continue
        folded = [by_name[name] for name in hide if name in by_name]
        hidden.update(skill.name for skill in folded)
        descriptions = [
            by_name[primary].description,
            *(skill.description for skill in folded),
        ]
        files = [primary]
        for name in extras:
            if name in by_name and name not in files:
                files.append(name)
        joined = " ".join(part for part in descriptions if part)
        load_paths = tuple(by_name[name].path for name in files if by_name[name].path)
        primaries[primary] = Skill(
            name=primary,
            description=clip_description(joined),
            path=by_name[primary].path,
            load=tuple(files),
            load_paths=load_paths,
        )
    collapsed: list[Skill] = []
    for skill in skills:
        if skill.name in hidden:
            continue
        collapsed.append(primaries.get(skill.name, skill))
    return collapsed


def scan_skills(home: Path) -> list[Skill]:
    seen: set[str] = set()
    skills: list[Skill] = []
    for root in SKILL_ROOTS:
        for path in sorted((home / root).glob("*/SKILL.md")):
            skill = load_skill(path)
            if skill is None or skill.name in seen:
                continue
            seen.add(skill.name)
            skills.append(skill)
    return skills


def load_skill(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = parse_frontmatter(text)
    name = (fields.get("name") or path.parent.name).strip()
    if not name:
        return None
    description = clip_description(fields.get("description") or "")
    resolved = str(path.resolve())
    return Skill(
        name=name,
        description=description,
        path=resolved,
        load_paths=(resolved,),
    )


def clip_description(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:DESCRIPTION_CHARS]


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    end = _frontmatter_end(lines)
    if end is None:
        return {}
    return _parse_fields(lines[1:end])


def skill_body(text: str) -> str:
    """SKILL.md text with its frontmatter removed."""
    lines = text.splitlines()
    end = _frontmatter_end(lines)
    return "\n".join(lines if end is None else lines[end + 1 :]).strip()


def _frontmatter_end(lines: list[str]) -> int | None:
    if not lines or lines[0].strip() != FRONTMATTER_MARK:
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_MARK:
            return index
    return None


def _parse_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line[:1].isspace() or ":" not in line:
            index += 1
            continue
        key, _, raw = line.partition(":")
        name = key.strip()
        value = raw.strip()
        if value in {">", "|", ">-", "|-", ">+", "|+"}:
            block, index = _indented_block(lines, index + 1)
            fields[name] = " ".join(block.split()) if value.startswith(">") else block
            continue
        fields[name] = _unquote(value)
        index += 1
    return fields


def _indented_block(lines: list[str], start: int) -> tuple[str, int]:
    chunks: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if line and not line[:1].isspace():
            break
        chunks.append(line.strip())
        index += 1
    return "\n".join(chunks).strip(), index


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
