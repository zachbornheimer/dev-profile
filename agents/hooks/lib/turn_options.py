"""Turn options: more than one skill, plus the tools the prompt needs.

TypeSafe pick-skill already returns a shortlist. The hook used to inject only
the winner. This module renders the shortlist and the matching tools so the
model sees options, not a single mandate.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_ROOT = Path.home() / ".agents/available-skills"
MAX_BODY_CHARS = 24_000

# Hermes tool names. The canary prompt is "Please do deep web research onthis".
HERMES_RESEARCH_TOOLS = (
    (
        re.compile(r"web research|deep research|deep web research", re.IGNORECASE),
        (
            ("hermes_web_search", "Search the web."),
            ("web_extract", "Fetch a page as text."),
            ("browser_exec", "Open a page when search or extract fails."),
        ),
    ),
)


def skill_file(name: str, root: Path = SKILL_ROOT) -> Path | None:
    path = root / name / "SKILL.md"
    return path if path.is_file() else None


def description_of(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")[:4000]
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    front = text[3 : end if end != -1 else 800]
    lines = front.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        rest = line.split(":", 1)[1].strip()
        if rest in {">", "|", ">-", "|-", "|+"}:
            parts = []
            for nxt in lines[index + 1 :]:
                if nxt and not nxt.startswith((" ", "\t")):
                    break
                parts.append(nxt.strip())
            return " ".join(part for part in parts if part)
        return rest.strip("\"'")
    return ""


def _higher_fit(choice: str, fits: dict) -> str:
    """Name of a shortlisted skill whose fit beats the picker choice. Empty if none."""

    chosen = fits.get(choice)
    if not isinstance(chosen, (int, float)):
        return ""
    best_name = ""
    best = float(chosen)
    for name, value in fits.items():
        if name == choice or not isinstance(value, (int, float)):
            continue
        if value > best:
            best = float(value)
            best_name = name
    return best_name


def matching_tools(
    prompt: str, rules: tuple = HERMES_RESEARCH_TOOLS
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen = set()
    for pattern, tools in rules:
        if not pattern.search(prompt):
            continue
        for name, why in tools:
            if name in seen:
                continue
            seen.add(name)
            found.append((name, why))
    return found


def render_turn_context(
    prompt: str,
    pick: dict | None,
    *,
    rules: tuple = HERMES_RESEARCH_TOOLS,
    root: Path = SKILL_ROOT,
) -> str | None:
    """Return turn context with skill options and tools, or None when there is nothing to inject."""

    pick = pick or {}
    choice = str(pick.get("choice") or "")
    if choice == "none":
        choice = ""
    shortlist = [
        name for name in pick.get("shortlist") or [] if isinstance(name, str) and name
    ]
    if choice and choice not in shortlist:
        shortlist.insert(0, choice)
    paths = [Path(item) for item in pick.get("paths") or [] if isinstance(item, str)]
    chosen_path = paths[0] if paths else (skill_file(choice, root) if choice else None)
    fits = pick.get("fits") if isinstance(pick.get("fits"), dict) else {}
    tools = matching_tools(prompt, rules)
    if not shortlist and not tools:
        return None

    higher = _higher_fit(choice, fits)
    lines = [
        "TypeSafe options for this request. Use what fits.",
        (
            f"Picker choice is {choice}. {higher} has a higher fit. Do not treat the choice as best."
            if higher
            else "The chosen skill is the best match, not the only option."
        ),
        "",
        "Skills:",
    ]
    for name in shortlist:
        path = chosen_path if name == choice and chosen_path else skill_file(name, root)
        fit = fits.get(name)
        if name == choice and higher:
            mark = "picker choice"
        elif name == higher:
            mark = "higher fit"
        elif name == choice:
            mark = "chosen"
        else:
            mark = "option"
        score = f", fit {fit:.2f}" if isinstance(fit, (int, float)) else ""
        desc = description_of(path) if path else ""
        lines.append(f"- {name} ({mark}{score})" + (f": {desc}" if desc else ""))
        if path:
            lines.append(f"  path: {path}")
    if choice and chosen_path and chosen_path.is_file():
        try:
            body = chosen_path.read_text(encoding="utf-8")[:MAX_BODY_CHARS]
        except OSError:
            body = ""
        if body:
            lines.append("")
            lines.append(f'<typesafe-skill name="{choice}" path="{chosen_path}">')
            lines.append(body)
            lines.append("</typesafe-skill>")
    if tools:
        lines.append("")
        lines.append("Tools:")
        for name, why in tools:
            lines.append(f"- {name}: {why}")
    return "\n".join(lines)
