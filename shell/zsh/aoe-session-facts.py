import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

TITLE_MAX = 120
PLACEHOLDERS = {"new session", "untitled", "untitled session"}
home = Path.home()


def cwd_from_slug(slug):
    if slug.startswith("--") and slug.endswith("--"):
        root, encoded = Path("/"), slug[2:-2]
    elif slug == "-tmp" or slug.startswith("-tmp-"):
        root, encoded = Path(tempfile.gettempdir()).resolve(), slug[5:]
    elif slug.startswith("-"):
        root, encoded = home, slug[1:]
    else:
        return ""

    def candidates(parent, remaining):
        if not remaining:
            return {str(parent.resolve())}
        found = set()
        try:
            for child in parent.iterdir():
                if not child.is_dir():
                    continue
                if child.name == remaining:
                    found.add(str(child.resolve()))
                elif remaining.startswith(child.name + "-"):
                    found.update(candidates(child, remaining[len(child.name) + 1 :]))
        except OSError:
            pass
        return found

    matches = candidates(root, encoded)
    return matches.pop() if len(matches) == 1 else ""


def omp_facts(session_id):
    root = home / ".omp" / "agent"
    buckets = set()
    cwd = title = ""
    for path in (root / "sessions").glob(f"*/*_{session_id}*"):
        if not (
            path.name.endswith("_" + session_id)
            or path.name.endswith("_" + session_id + ".jsonl")
        ):
            continue
        buckets.add(path.parent.name)
        if path.suffix != ".jsonl" or not path.is_file():
            continue
        try:
            with path.open() as handle:
                # omp stores its title and session header before conversation entries.
                for _ in range(2):
                    line = handle.readline()
                    if not line:
                        break
                    obj = json.loads(line)
                    if obj.get("type") == "title":
                        title = str(obj.get("title") or "")
                    elif obj.get("type") == "session" and obj.get("id") == session_id:
                        cwd = str(obj.get("cwd") or "")
                        title = title or str(obj.get("title") or "")
        except (OSError, ValueError):
            continue
    if not cwd and len(buckets) == 1:
        cwd = cwd_from_slug(buckets.pop())
    db = root / "history.db"
    if db.is_file():
        try:
            with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                row = con.execute(
                    "SELECT title FROM session_titles WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row:
                    title = str(row[0] or "")
        except sqlite3.Error:
            pass
    return cwd, title


def codex_name(session_id):
    best = None
    best_n = -1
    for cand in (home / ".codex").glob("state_*.sqlite"):
        try:
            number = int(cand.stem.rsplit("_", 1)[-1])
        except ValueError:
            continue
        if number > best_n:
            best, best_n = cand, number
    if best is None:
        return "", ""
    try:
        with closing(sqlite3.connect(f"file:{best}?mode=ro", uri=True)) as con:
            row = con.execute(
                "SELECT cwd, name FROM threads WHERE id = ?", (session_id,)
            ).fetchone()
    except sqlite3.Error:
        return "", ""
    if not row:
        return "", ""
    return str(row[0] or ""), str(row[1] or "").strip()


def sanitize(title):
    title = " ".join(title.split())
    if title.lower() in PLACEHOLDERS:
        return ""
    if len(title) > TITLE_MAX:
        cut = title[:TITLE_MAX]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        title = cut.strip() or title[:TITLE_MAX]
    return title


def main():
    harness, _, session_id = sys.argv[1].partition(":")
    cwd = title = ""
    if (
        session_id
        and "/" not in session_id
        and not any(c in session_id for c in "*?[]")
    ):
        if harness == "omp":
            cwd, title = omp_facts(session_id)
        elif harness == "codex":
            cwd, title = codex_name(session_id)
    sys.stdout.write(cwd + "\n" + sanitize(title) + "\n")


if __name__ == "__main__":
    main()
