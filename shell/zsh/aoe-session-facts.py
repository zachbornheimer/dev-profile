import json
import os
import sqlite3
import subprocess
import sys
import urllib.parse
from pathlib import Path

TITLE_MAX = 120
CLAUDE_FULL_SCAN = 8 * 1024 * 1024
CLAUDE_WINDOW = 512 * 1024
PLACEHOLDERS = {"new session", "untitled", "untitled session"}

ref = sys.argv[1]
find_session = Path(sys.argv[2])
find_transcript = Path(sys.argv[3])
extract_context = Path(sys.argv[4])
harness, _, session_id = ref.partition(":")
home = Path.home()


def run(argv):
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def first_obj(raw):
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def summary_beside(transcript):
    if not transcript or transcript.startswith("sqlite:"):
        return {}
    summary = Path(transcript).parent / "summary.json"
    if not summary.is_file():
        return {}
    try:
        data = json.loads(summary.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def cwd_from_transcript(transcript):
    info = summary_beside(transcript).get("info") or {}
    if isinstance(info, dict) and info.get("cwd"):
        return str(info["cwd"])
    if "/.grok/sessions/" in transcript.replace("\\", "/"):
        return urllib.parse.unquote(Path(transcript).parent.parent.name)
    return ""


def claude_title(path):
    custom = ""
    ai = ""

    def take(blob):
        nonlocal custom, ai
        for line in blob.decode("utf-8", "replace").splitlines():
            if "custom-title" not in line and "ai-title" not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = obj.get("type")
            if kind == "custom-title":
                title = str(obj.get("customTitle") or "").strip()
                if title:
                    custom = title
            elif kind == "ai-title":
                title = str(obj.get("aiTitle") or "").strip()
                if title:
                    ai = title

    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size <= CLAUDE_FULL_SCAN:
                take(handle.read())
            else:
                take(handle.read(CLAUDE_WINDOW))
                handle.seek(max(0, size - CLAUDE_WINDOW))
                handle.readline()
                take(handle.read())
    except OSError:
        return ""
    return custom or ai


def title_from_transcript(transcript):
    if not transcript or transcript.startswith("sqlite:"):
        return ""
    generated = str(summary_beside(transcript).get("generated_title") or "").strip()
    if generated:
        return generated
    path = Path(transcript)
    if path.is_file() and path.suffix == ".jsonl":
        return claude_title(path)
    return ""


def codex_name(session_id):
    root = home / ".codex"
    best = None
    best_n = -1
    if not root.is_dir():
        return ""
    for cand in root.glob("state_*.sqlite"):
        try:
            number = int(cand.stem.rsplit("_", 1)[-1])
        except ValueError:
            continue
        if number > best_n:
            best, best_n = cand, number
    if best is None:
        return ""
    try:
        con = sqlite3.connect(f"file:{best}?mode=ro", uri=True)
        row = con.execute(
            "SELECT name FROM threads WHERE id = ?", (session_id,)
        ).fetchone()
    except sqlite3.Error:
        return ""
    if not row or not row[0]:
        return ""
    return str(row[0]).strip()


def opencode_facts(session_id):
    db = Path(
        os.environ.get("OPENCODE_DB")
        or (
            Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
            / "opencode/opencode.db"
        )
    )
    if not db.is_file():
        return ("", "")
    ids = [session_id]
    if session_id.startswith("ses_"):
        ids.append(session_id[4:])
    else:
        ids.append("ses_" + session_id)
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return ("", "")
    for table in ("session_v2", "session"):
        for one in ids:
            try:
                row = con.execute(
                    f"SELECT directory, title FROM {table} WHERE id = ?", (one,)
                ).fetchone()
            except sqlite3.Error:
                continue
            if row:
                return str(row[0] or "").strip(), str(row[1] or "").strip()
    return ("", "")


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
    cwd = ""
    transcript = ""
    title = ""
    if find_session.is_file():
        obj = first_obj(run(["python3", str(find_session), ref]))
        cwd = str(obj.get("cwd") or "")
        transcript = str(obj.get("transcript_path") or "")
        if not cwd and transcript:
            cwd = cwd_from_transcript(transcript)
        title = title_from_transcript(transcript)
    if not transcript and find_transcript.is_file() and harness and session_id:
        found = run(["bash", str(find_transcript), harness, session_id]).strip()
        if found and not found.startswith("ERROR"):
            transcript = found.splitlines()[-1].strip()
    if (
        transcript
        and not cwd
        and extract_context.is_file()
        and not transcript.startswith("sqlite:")
        and Path(transcript).is_file()
    ):
        obj = first_obj(run(["python3", str(extract_context), harness, transcript]))
        cwd = str(obj.get("working_dir") or obj.get("cwd") or "")
    if transcript and not title:
        title = title_from_transcript(transcript)
    if not title and harness == "codex":
        title = codex_name(session_id)
    if harness == "opencode" and (not cwd or not title):
        native_cwd, native_title = opencode_facts(session_id)
        cwd = cwd or native_cwd
        title = title or native_title
    sys.stdout.write(cwd + "\n" + sanitize(title) + "\n")


if __name__ == "__main__":
    main()
