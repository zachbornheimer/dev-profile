"""classify-file observation, prefilter, and TypeSafe request/decide."""

from __future__ import annotations

import json
import os
import re
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import answers
from constants import (
    FILE_CATALOG_BASENAME_BONUS,
    FILE_DEST_LIFE,
    FILE_DIR_SAMPLE_FILE_CHARS,
    FILE_DIR_SAMPLE_FILE_COUNT,
    FILE_DIR_SAMPLE_MAX_DEPTH,
    FILE_DISPOSITION_ARCHIVE,
    FILE_DISPOSITION_ATTACH_EVIDENCE,
    FILE_DISPOSITION_CONFIDENCE_FLOORS,
    FILE_DISPOSITION_FILE_TO_LINEAR,
    FILE_DISPOSITION_KEEP,
    FILE_DISPOSITION_MOVE_TO_REPO,
    FILE_DISPOSITION_PERSONAL_DOCS,
    FILE_DISPOSITION_TRASH_CANDIDATE,
    FILE_DISPOSITIONS,
    FILE_EXTRACT_TIMEOUT_SECONDS,
    FILE_FLAG_BACKUP,
    FILE_FLAG_EVIDENCE,
    FILE_FLAG_FLOORS,
    FILE_FLAG_ISSUE_LIST,
    FILE_FLAG_LOSS_RECORD,
    FILE_FLAG_PRIVATE,
    FILE_FLAG_REGENERABLE,
    FILE_FLAGS,
    FILE_KIND_BACKUP,
    FILE_KIND_DATA_DUMP,
    FILE_KIND_DOCUMENT,
    FILE_KIND_EVIDENCE,
    FILE_KIND_ISSUE_LIST,
    FILE_KIND_MEDIA,
    FILE_KIND_SCRATCH,
    FILE_KIND_SCREENSHOT,
    FILE_KIND_SCRIPT,
    FILE_KIND_SPEC,
    FILE_KINDS,
    FILE_LEGAL_DISPOSITIONS_BY_PROJECT_KIND,
    FILE_LOSS_RECORD_FILENAME_TOKENS,
    FILE_MAX_DIR_ENTRIES,
    FILE_PERSONAL_BUCKET_CRITERIA,
    FILE_PERSONAL_DESTINATIONS,
    FILE_PREFILTER_CONFIDENCE,
    FILE_PREFILTER_MEDIA_CONFIDENCE,
    FILE_PROJECT_CANDIDATE_LIMIT,
    FILE_PROJECT_KIND_LINEAR,
    FILE_PROJECT_KIND_NONE,
    FILE_PROJECT_KIND_PERSONAL,
    FILE_PROJECT_KIND_REPO,
    FILE_PROJECT_MATCH_THRESHOLD,
    FILE_PROJECT_NONE,
    FILE_SCORING_EXCERPT_CHARS,
    FILE_STRONG_MATCH_MAX_DOCUMENT_FREQUENCY,
    FILE_TEXT_CONTENT_BYTES,
    LOCAL_PICK_MIN_TOKEN_LENGTH,
    LOCAL_PICK_STOPWORDS,
    MODEL,
    REASON_BELOW_CONFIDENCE,
    REASON_FILE_BACKUP_PATTERN,
    REASON_FILE_EVIDENCE_NEEDS_TRIAGE,
    REASON_FILE_ILLEGAL_DISPOSITION,
    REASON_FILE_ISSUE_NEEDS_TRIAGE,
    REASON_FILE_LOSS_RECORD_GUARD,
    REASON_FILE_MEDIA_EXTENSION,
    REASON_FILE_PRIVATE_GUARD,
    REASON_FILE_SCREENSHOT_PATTERN,
    REASON_SELECTED,
    REASON_UNAVAILABLE,
)

QUESTION_KIND = "kind"
CANDIDATE_QUESTION_PREFIX = "match_"
STRONG_MATCH_PROBABILITY = 1.0
# Kinds a repo document can move into that repo's docs/ (design rule R4) — evidence,
# screenshot, media, backup, and scratch kinds are never filed into a repo this way.
FILE_KINDS_MOVABLE_TO_REPO = frozenset(
    {
        FILE_KIND_SPEC,
        FILE_KIND_DOCUMENT,
        FILE_KIND_ISSUE_LIST,
        FILE_KIND_SCRIPT,
        FILE_KIND_DATA_DUMP,
    }
)

# Extensions with no text representation classify-file can extract; observed but not
# read (images, video, audio, proprietary iWork/disk-image bundles).
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".heic", ".heif"})
VIDEO_EXTENSIONS = frozenset({".mov", ".mp4", ".m4v"})
UNREADABLE_EXTENSIONS = (
    IMAGE_EXTENSIONS
    | VIDEO_EXTENSIONS
    | frozenset({".dmg", ".pages", ".key", ".numbers", ".mp3", ".m4a"})
)
# Kept as an alias for the extension set unit tests and callers reasonably expect to
# mean "classify-file will not read this file's bytes as content".
BINARY_EXTENSIONS = UNREADABLE_EXTENSIONS

DOCX_LIKE_EXTENSIONS = frozenset({".docx", ".doc", ".rtf"})
PDF_EXTENSION = ".pdf"
ZIP_EXTENSION = ".zip"
HTML_EXTENSIONS = frozenset({".html", ".htm"})
TEXT_LIKE_EXTENSIONS = (
    frozenset(
        {
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".csv",
            ".log",
            ".py",
            ".go",
            ".js",
            ".ts",
            ".sh",
            ".xml",
            ".curl",
            ".conf",
            ".toml",
            ".ini",
        }
    )
    | HTML_EXTENSIONS
    | DOCX_LIKE_EXTENSIONS
)

SCREENSHOT_NAME_PREFIXES = ("screenshot", "screen shot")
BACKUP_NAME_SUFFIXES = (".bkup", ".bak")

KIND_CRITERIA = {
    FILE_KIND_SPEC: "A design, ADR, or planning document for a specific project.",
    FILE_KIND_ISSUE_LIST: "A list of bugs, tasks, or tickets to file.",
    FILE_KIND_EVIDENCE: "A log, transcript, or screenshot captured as proof of a bug or result.",
    FILE_KIND_DATA_DUMP: "Raw JSON/CSV/export data with no narrative.",
    FILE_KIND_SCRIPT: "Source code or a runnable script.",
    FILE_KIND_SCREENSHOT: "A screen capture image.",
    FILE_KIND_MEDIA: "A photo, video, or audio file that is not a screenshot.",
    FILE_KIND_DOCUMENT: "Prose: biography, paperwork, correspondence, or notes.",
    FILE_KIND_BACKUP: "A duplicate or backup copy of another file.",
    FILE_KIND_SCRATCH: "Throwaway scratch content with no lasting value.",
}
# The 5 disposition flag Nouls (design section 2.2): each is one atomic yes/no
# proposition TypeSafe answers with a probability, and `decide()` composes them with
# `project`/`kind` into a disposition via rules R1-R9 — disposition is computed, never
# asked as a Choice, so the model can never be forced to guess before the project (and
# thus the legal dispositions) is known.
FLAG_QUESTIONS = {
    FILE_FLAG_BACKUP: (
        "Is this file a backup, export copy, or duplicate of data that also exists "
        "elsewhere, rather than the primary copy? Use `filename`, `entries`, `excerpt`."
    ),
    FILE_FLAG_ISSUE_LIST: (
        "Is `excerpt` primarily a list of bugs, tasks, or problems that still need doing?"
    ),
    FILE_FLAG_EVIDENCE: (
        "Is this captured output — a log, transcript, test/proof run, or diagnostic "
        "bundle — rather than authored prose or code?"
    ),
    FILE_FLAG_PRIVATE: (
        "Do `excerpt` or `entries` contain credentials, license/activation data, "
        "email/mail archives, or private personal information?"
    ),
    FILE_FLAG_REGENERABLE: (
        "Could this file be recreated at will by re-running a tool or re-exporting, "
        "so deleting it loses nothing?"
    ),
    FILE_FLAG_LOSS_RECORD: (
        "Does this file record data that was lost, missing, deleted, or unrecovered — "
        "an inventory of missing files, a coverage/gap report, or a recovery manifest "
        "— such that it may be the only record of what is gone? Use `filename`, "
        "`excerpt`, `entries`, and `loss_record_hint`."
    ),
}


@dataclass(frozen=True, slots=True)
class FileResult:
    path: str
    project: str
    kind: str
    disposition: str
    destination_hint: str
    confidence: float
    reason: str
    # True when the disposition is deliberately deferred to a human/agent triage step
    # (F2: an issue list, or evidence, with no Linear project to attach to) rather
    # than resolved — a distinct signal from "keep because nothing was confident
    # enough".
    needs_triage: bool = False
    # True for attach-evidence: the agent step must still pick the exact Linear issue
    # (from the filename, a ticket id in the name/content, or recent issues for the
    # project) before the upload can happen.
    needs_ticket: bool = False
    # True for attach-evidence when the private flag fired: the agent step uploads a
    # redacted copy, never the raw file.
    needs_redaction: bool = False
    # True when `flag_private` or `flag_loss_record` fired (design: both are treated
    # as seriously as each other) -- a signal to the human/agent reviewer that this
    # file needs eyes-on before it is touched, independent of which disposition the
    # rule chain landed on.
    important: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "project": self.project,
            "kind": self.kind,
            "disposition": self.disposition,
            "destination_hint": self.destination_hint,
            "confidence": self.confidence,
            "reason": self.reason,
            "needs_triage": self.needs_triage,
            "needs_ticket": self.needs_ticket,
            "needs_redaction": self.needs_redaction,
            "important": self.important,
        }


def fallback(path: str, reason: str = REASON_UNAVAILABLE) -> FileResult:
    return FileResult(
        path=path,
        project=FILE_PROJECT_NONE,
        kind=FILE_KIND_SCRATCH,
        disposition=FILE_DISPOSITION_KEEP,
        destination_hint="",
        confidence=0.0,
        reason=reason,
    )


TextExtractor = Any  # Callable[[Path], str | None] facades for textutil/pdftotext


def _run_textutil(path: Path) -> str | None:
    """Extract text from docx/doc/rtf via macOS `textutil`. None on any failure."""
    try:
        completed = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=FILE_EXTRACT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _run_pdftotext(path: Path) -> str | None:
    """Extract text from a PDF via poppler's `pdftotext`, when installed."""
    try:
        completed = subprocess.run(
            ["pdftotext", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=FILE_EXTRACT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _read_raw_text(path: Path) -> str:
    try:
        raw = path.read_bytes()[:FILE_TEXT_CONTENT_BYTES]
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_NOISE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(raw: str) -> str:
    text = _HTML_NOISE_RE.sub(" ", raw)
    text = _HTML_TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_zip_text(path: Path) -> str | None:
    """First text-like member of a zip (or a .pages/.key iWork bundle, which is a
    zip container) — sorted for determinism, not necessarily reading order."""
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if Path(name).suffix.lower() not in TEXT_LIKE_EXTENSIONS:
                    continue
                with archive.open(name) as member:
                    raw = member.read(FILE_TEXT_CONTENT_BYTES)
                return raw.decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def _extract_text_for(
    path: Path, extension: str, run_textutil: TextExtractor, run_pdftotext: TextExtractor
) -> str:
    """Dispatch content extraction by extension. Fails open to "" — a file classify-file
    cannot read text from is still classified from its filename and metadata."""
    if extension in DOCX_LIKE_EXTENSIONS:
        return run_textutil(path) or ""
    if extension == PDF_EXTENSION:
        return run_pdftotext(path) or ""
    if extension == ZIP_EXTENSION:
        return _extract_zip_text(path) or ""
    if extension in HTML_EXTENSIONS:
        raw = _read_raw_text(path)
        return _strip_html(raw) if raw else ""
    if extension in UNREADABLE_EXTENSIONS:
        return ""
    return _read_raw_text(path)


def _dir_entries(path: Path) -> list[str]:
    try:
        names = sorted(entry.name for entry in path.iterdir())
    except OSError:
        return []
    return names[:FILE_MAX_DIR_ENTRIES]


def _sample_dir_text(path: Path, run_textutil: TextExtractor, run_pdftotext: TextExtractor) -> str:
    """Text of the first few text-like files found inside a directory or bundle (e.g.
    a .scriv project), bounded in count, size, and walk depth."""
    collected: list[str] = []
    for root, dirs, files in os.walk(path):
        depth = len(Path(root).relative_to(path).parts)
        if depth >= FILE_DIR_SAMPLE_MAX_DEPTH:
            dirs[:] = []
        for name in sorted(files):
            if len(collected) >= FILE_DIR_SAMPLE_FILE_COUNT:
                return "\n\n".join(collected)
            file_path = Path(root) / name
            extension = file_path.suffix.lower()
            if extension not in TEXT_LIKE_EXTENSIONS:
                continue
            text = _extract_text_for(file_path, extension, run_textutil, run_pdftotext)
            if not text.strip():
                continue
            collected.append(f"{name}:\n{text[:FILE_DIR_SAMPLE_FILE_CHARS]}")
    return "\n\n".join(collected)


def observe(
    path: Path,
    *,
    run_textutil: TextExtractor | None = None,
    run_pdftotext: TextExtractor | None = None,
) -> dict[str, Any]:
    """Read filename/extension/size/mtime and real content (bounded) — read-only.
    Text files are read directly; docx/pdf/html/zip get extracted text; directories
    (including .scriv bundles) get a listing plus the text of a few files inside."""
    extract_text = run_textutil if run_textutil is not None else _run_textutil
    extract_pdf = run_pdftotext if run_pdftotext is not None else _run_pdftotext
    resolved = path.expanduser()
    try:
        stat_result = resolved.stat()
    except OSError as exc:
        raise FileNotFoundError(str(resolved)) from exc
    is_dir = resolved.is_dir()
    observation: dict[str, Any] = {
        "path": str(resolved),
        "filename": resolved.name,
        "extension": resolved.suffix.lower(),
        "size": stat_result.st_size,
        "mtime": datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat(),
        "is_dir": is_dir,
        "excerpt": "",
        "entries": [],
    }
    if is_dir:
        observation["entries"] = _dir_entries(resolved)
        observation["excerpt"] = _sample_dir_text(resolved, extract_text, extract_pdf)[
            :FILE_TEXT_CONTENT_BYTES
        ]
        return observation
    observation["excerpt"] = _extract_text_for(
        resolved, observation["extension"], extract_text, extract_pdf
    )[:FILE_TEXT_CONTENT_BYTES]
    return observation


def _looks_like_backup(filename: str) -> bool:
    lowered = filename.lower()
    if lowered.endswith(BACKUP_NAME_SUFFIXES):
        return True
    stem = Path(filename).stem.lower()
    if stem.endswith(("-old", " old")):
        return True
    if stem.endswith(" copy"):
        return True
    parts = stem.rsplit(" copy ", 1)
    return len(parts) == 2 and parts[1].strip().isdigit()


def _looks_like_screenshot(filename: str) -> bool:
    return filename.lower().startswith(SCREENSHOT_NAME_PREFIXES)


def prefilter(observation: dict[str, Any]) -> FileResult | None:
    """Deterministic classification for the unambiguous cases; None means ask TypeSafe."""
    if observation["is_dir"]:
        return None
    filename = observation["filename"]
    extension = observation["extension"]
    path = observation["path"]
    if _looks_like_backup(filename):
        return FileResult(
            path=path,
            project=FILE_PROJECT_NONE,
            kind=FILE_KIND_BACKUP,
            disposition=FILE_DISPOSITION_TRASH_CANDIDATE,
            destination_hint="",
            confidence=FILE_PREFILTER_CONFIDENCE,
            reason=REASON_FILE_BACKUP_PATTERN,
        )
    if extension in IMAGE_EXTENSIONS and _looks_like_screenshot(filename):
        return FileResult(
            path=path,
            project=FILE_PROJECT_NONE,
            kind=FILE_KIND_SCREENSHOT,
            disposition=FILE_DISPOSITION_ARCHIVE,
            destination_hint=FILE_DEST_LIFE,
            confidence=FILE_PREFILTER_CONFIDENCE,
            reason=REASON_FILE_SCREENSHOT_PATTERN,
        )
    if extension in IMAGE_EXTENSIONS or extension in VIDEO_EXTENSIONS:
        return FileResult(
            path=path,
            project=FILE_PROJECT_NONE,
            kind=FILE_KIND_MEDIA,
            disposition=FILE_DISPOSITION_ARCHIVE,
            destination_hint=FILE_DEST_LIFE,
            confidence=FILE_PREFILTER_MEDIA_CONFIDENCE,
            reason=REASON_FILE_MEDIA_EXTENSION,
        )
    return None


def load_catalog(path: str) -> list[dict[str, Any]]:
    """Load repo-catalog.json entries; fail open to an empty list."""
    if not path:
        return []
    try:
        raw = Path(path).expanduser().read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, TypeError, ValueError):
        return []
    entries = payload.get("repos") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def load_linear_projects(raw: str) -> list[dict[str, Any]]:
    """Parse an inline JSON list of Linear project names/objects; fail open to []."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    projects: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict) and item.get("name"):
            projects.append({"name": str(item["name"])})
        elif isinstance(item, str) and item.strip():
            projects.append({"name": item.strip()})
    return projects


def _catalog_by_name(catalog_entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for entry in catalog_entries:
        full_name = str(entry.get("full_name") or "").strip()
        if full_name:
            by_name[full_name] = entry
    return by_name


_WORD_RE = re.compile(r"[a-z0-9]+")
# Generic descriptor words common to both filenames and repo keywords/descriptions —
# carry no project-identifying signal, so a rare-in-this-catalog accident (e.g. "proof"
# appearing in exactly one repo's keywords) must not outscore a genuinely distinctive
# token (e.g. "obsidian"). Kept local: this is a scoring heuristic, not shared policy.
FILE_GENERIC_SCORING_STOPWORDS = frozenset(
    {
        "live",
        "test",
        "tests",
        "testing",
        "proof",
        "demo",
        "data",
        "file",
        "files",
        "new",
        "old",
        "final",
        "draft",
        "notes",
        "note",
        "plan",
        "review",
        "docs",
        "doc",
        "report",
        "summary",
        "copy",
        "backup",
        "output",
        "input",
        "log",
        "logs",
        "list",
        "misc",
        "temp",
        "tmp",
    }
)


def _words(text: str) -> set[str]:
    """Tokenize into scoring-length words (mirrors pick.py's local-match tokenizer),
    excluding generic descriptor words that carry no project-identifying signal."""
    tokens: set[str] = set()
    for raw in _WORD_RE.findall(text.lower()):
        if (
            len(raw) < LOCAL_PICK_MIN_TOKEN_LENGTH
            or raw in LOCAL_PICK_STOPWORDS
            or raw in FILE_GENERIC_SCORING_STOPWORDS
        ):
            continue
        tokens.add(raw)
    return tokens


def _repo_basename(full_name: str) -> str:
    return full_name.rsplit("/", 1)[-1].lower()


def _is_generic_word(word: str) -> bool:
    return word in LOCAL_PICK_STOPWORDS or word in FILE_GENERIC_SCORING_STOPWORDS


def _filename_raw_segments(filename: str) -> set[str]:
    """Hyphen/underscore/space/dot-separated filename segments, unfiltered by length
    (so short but meaningful names like "zq" and "evo" are not dropped) but excluding
    generic descriptor words (so "proof"/"live" cannot masquerade as an identity
    signal just because a filename happens to contain them)."""
    stem = Path(filename).stem.lower()
    return {
        segment
        for segment in re.split(r"[-_ .]+", stem)
        if segment and not _is_generic_word(segment)
    }


def _catalog_entry_tokens(entry: dict[str, Any]) -> set[str]:
    basename = _repo_basename(str(entry.get("full_name") or ""))
    tokens = _words(basename.replace("-", " "))
    tokens.add(basename)
    for keyword in entry.get("keywords") or []:
        text = str(keyword).lower()
        tokens |= _words(text.replace("-", " "))
        if not _is_generic_word(text):
            tokens.add(text)
    return tokens


def _observation_tokens(observation: dict[str, Any]) -> set[str]:
    stem = Path(observation["filename"]).stem
    tokens = _words(stem.replace("-", " ").replace("_", " "))
    tokens |= _filename_raw_segments(observation["filename"])
    tokens |= _words(observation.get("excerpt", "")[:FILE_SCORING_EXCERPT_CHARS])
    return tokens


def _catalog_token_document_frequency(
    catalog_entries: list[dict[str, Any]],
) -> dict[str, int]:
    """How many catalog repos carry each token — the rarity signal that separates a
    distinctive match (e.g. "agentmux", 1 repo) from an ambiguous one (e.g.
    "obsidian", 3 repos)."""
    document_frequency: dict[str, int] = {}
    for entry in catalog_entries:
        for token in _catalog_entry_tokens(entry):
            document_frequency[token] = document_frequency.get(token, 0) + 1
    return document_frequency


def _catalog_matches(
    observation: dict[str, Any], catalog_entries: list[dict[str, Any]]
) -> list[tuple[str, float, bool]]:
    """Score every catalog repo against the file's tokens. Returns (full_name, score,
    is_exact_basename_or_keyword_match) sorted highest score first."""
    document_frequency = _catalog_token_document_frequency(catalog_entries)
    obs_tokens = _observation_tokens(observation)
    raw_segments = _filename_raw_segments(observation["filename"])
    scored: list[tuple[str, float, bool]] = []
    for entry in catalog_entries:
        full_name = str(entry.get("full_name") or "").strip()
        if not full_name:
            continue
        entry_tokens = _catalog_entry_tokens(entry)
        overlap = obs_tokens & entry_tokens
        if not overlap:
            continue
        score = sum(1.0 / document_frequency.get(token, 1) for token in overlap)
        basename = _repo_basename(full_name)
        is_exact = basename in raw_segments or bool(
            raw_segments & {str(k).lower() for k in entry.get("keywords") or []}
        )
        if is_exact:
            score += FILE_CATALOG_BASENAME_BONUS
        scored.append((full_name, score, is_exact))
    scored.sort(key=lambda item: -item[1])
    return scored


def _linear_matches(
    observation: dict[str, Any], linear_projects: list[dict[str, Any]]
) -> list[tuple[str, float, bool]]:
    obs_tokens = _observation_tokens(observation)
    raw_segments = _filename_raw_segments(observation["filename"])
    scored: list[tuple[str, float, bool]] = []
    for project in linear_projects:
        name = str(project.get("name") or "").strip()
        if not name:
            continue
        project_tokens = _words(name.replace("-", " "))
        overlap = obs_tokens & project_tokens
        if not overlap:
            continue
        is_exact = bool(raw_segments & {token.lower() for token in project_tokens})
        scored.append((f"linear:{name}", float(len(overlap)), is_exact))
    scored.sort(key=lambda item: -item[1])
    return scored


def _normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def strong_project_match(
    observation: dict[str, Any], catalog_entries: list[dict[str, Any]]
) -> str | None:
    """A repo whose basename or *canonical* keyword (by catalog convention, the first
    keyword — e.g. evident-output's "evo", zq's "zq") is both an exact filename segment
    and rare enough across the catalog to be unambiguous — decide `project` without a
    model call. Only the first keyword counts: an incidental, non-identifying keyword
    further down the list (e.g. "proof") must never trigger a guess. None means the
    signal is missing or too ambiguous (e.g. shared by several repos); the caller must
    ask TypeSafe instead of guessing."""
    document_frequency = _catalog_token_document_frequency(catalog_entries)
    raw_segments = _filename_raw_segments(observation["filename"])
    best: tuple[str, float] | None = None
    for entry in catalog_entries:
        full_name = str(entry.get("full_name") or "").strip()
        if not full_name:
            continue
        basename = _repo_basename(full_name)
        keywords = entry.get("keywords") or []
        canonical_keyword = str(keywords[0]).lower() if keywords else ""
        signals = {basename} | ({canonical_keyword} if canonical_keyword else set())
        for signal in signals:
            if signal not in raw_segments:
                continue
            token_key = signal if " " not in signal and "-" not in signal else basename
            if document_frequency.get(token_key, document_frequency.get(signal, 99)) > (
                FILE_STRONG_MATCH_MAX_DOCUMENT_FREQUENCY
            ):
                continue
            score = 1.0 / document_frequency.get(signal, 1)
            if best is None or score > best[1]:
                best = (full_name, score)
            elif score == best[1] and full_name != best[0]:
                return None  # tie between two distinct repos: too ambiguous to guess
            break
    return best[0] if best else None


def _shortlist(
    observation: dict[str, Any],
    catalog_entries: list[dict[str, Any]],
    linear_projects: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Deterministic candidate generation (typesafe-skills examples 14/19): cheap
    lexical scoring narrows 165+ repos and every Linear project down to a short,
    judgeable list. Returns ordered (project_key, description) pairs — the top scored
    repo/Linear candidates, then the always-offered personal:* buckets. TypeSafe judges
    only this shortlist; it never sees the whole catalog as a single Choice."""
    catalog_scored = _catalog_matches(observation, catalog_entries)
    shadowed_by_repo = {_normalize_name(_repo_basename(name)) for name, _, _ in catalog_scored}
    linear_scored = [
        item
        for item in _linear_matches(observation, linear_projects)
        if _normalize_name(item[0].removeprefix("linear:")) not in shadowed_by_repo
    ]
    combined = sorted(catalog_scored + linear_scored, key=lambda item: -item[1])
    top_candidates = combined[:FILE_PROJECT_CANDIDATE_LIMIT]

    catalog_by_name = _catalog_by_name(catalog_entries)
    shortlist: list[tuple[str, str]] = []
    for name, _score, _exact in top_candidates:
        if name.startswith("linear:"):
            project_name = name.removeprefix("linear:")
            description = (
                f"Linear project {project_name}; file belongs there as a ticket "
                "attachment, not a repo."
            )
            shortlist.append((name, description))
            continue
        entry = catalog_by_name.get(name, {})
        description = str(entry.get("description_proposed") or "").strip()
        keywords = entry.get("keywords")
        keyword_text = (
            ", ".join(str(word) for word in keywords if word) if isinstance(keywords, list) else ""
        )
        shortlist.append((name, description or keyword_text or name))
    shortlist.extend(FILE_PERSONAL_BUCKET_CRITERIA.items())
    return shortlist


def loss_record_filename_hint(filename: str) -> bool:
    """Deterministic prior for `flag_loss_record` (design section 11): a filename
    segment like "missing"/"lost"/"unrecovered"/"coverage" raises attention on the
    question via `state.loss_record_hint`, but the model's own Noul answer -- gated
    by `FILE_FLAG_FLOORS["loss_record"]` -- is always what decides the disposition."""
    return bool(_filename_raw_segments(filename) & FILE_LOSS_RECORD_FILENAME_TOKENS)


def _observation_state(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": observation["filename"],
        "extension": observation["extension"],
        "size": observation["size"],
        "mtime": observation["mtime"],
        "is_dir": observation["is_dir"],
        "excerpt": observation["excerpt"],
        "entries": observation["entries"],
        "loss_record_hint": loss_record_filename_hint(observation["filename"]),
    }


def project_kind(project: str) -> str:
    """Classify `project` into the coarse bucket that bounds its legal dispositions."""
    if project == FILE_PROJECT_NONE:
        return FILE_PROJECT_KIND_NONE
    if project.startswith("linear:"):
        return FILE_PROJECT_KIND_LINEAR
    if project in FILE_PERSONAL_DESTINATIONS:
        return FILE_PROJECT_KIND_PERSONAL
    return FILE_PROJECT_KIND_REPO


def legal_dispositions_for(project: str) -> tuple[str, ...]:
    return FILE_LEGAL_DISPOSITIONS_BY_PROJECT_KIND[project_kind(project)]


def _candidate_question(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": (
            f'Does this file belong to "{name}" — {description} Base your answer on '
            "`filename`, `excerpt`, and `entries`."
        ),
    }


def build_request(
    observation: dict[str, Any],
    catalog_entries: list[dict[str, Any]],
    linear_projects: list[dict[str, Any]],
    *,
    project: str | None = None,
) -> dict[str, Any]:
    """One batched TypeSafe call (typesafe-skills rule 4 / example 13): a per-candidate
    relevance Noul for each shortlisted project (re-rank/entity-alignment pattern, see
    examples 14/19), a kind Choice, and the 5 disposition flag Nouls -- never a Choice
    across the whole catalog, and never a disposition Choice asked before `project` is
    known (design section 4.1: disposition is computed by `decide()`, not asked).
    `project` pre-empts the shortlist when `strong_project_match` already resolved it
    deterministically; only kind/flags are then asked."""
    questions: dict[str, Any] = {}
    if project is None:
        shortlist = _shortlist(observation, catalog_entries, linear_projects)
        for index, (name, description) in enumerate(shortlist):
            questions[f"{CANDIDATE_QUESTION_PREFIX}{index}"] = _candidate_question(
                name, description
            )
    questions[QUESTION_KIND] = {
        "type": "choice",
        "instructions": "What kind of file is this?",
        "criteria": dict(KIND_CRITERIA),
    }
    for flag_id, instructions in FLAG_QUESTIONS.items():
        questions[flag_id] = {"type": "noul", "instructions": instructions}
    state = _observation_state(observation)
    if project is not None:
        state["project"] = project
    return {"model": MODEL, "state": state, "questions": questions}


def destination_hint_for(
    project: str, disposition: str, catalog_by_name: dict[str, dict[str, Any]]
) -> str:
    if disposition in (FILE_DISPOSITION_TRASH_CANDIDATE, FILE_DISPOSITION_KEEP):
        return ""
    if disposition in (FILE_DISPOSITION_FILE_TO_LINEAR, FILE_DISPOSITION_ATTACH_EVIDENCE):
        return ""
    if project in FILE_PERSONAL_DESTINATIONS:
        return FILE_PERSONAL_DESTINATIONS[project]
    if project.startswith("linear:"):
        return ""
    entry = catalog_by_name.get(project)
    local_path = str(entry.get("local_path") or "").strip() if entry else ""
    if local_path:
        return str(Path(local_path).expanduser() / "docs")
    return ""


def _resolve_project(
    answers_by_id: dict[str, Any],
    observation: dict[str, Any],
    catalog_entries: list[dict[str, Any]],
    linear_projects: list[dict[str, Any]],
) -> tuple[str, float]:
    """Highest-probability candidate that clears `FILE_PROJECT_MATCH_THRESHOLD`, or
    "none" -- never the raw argmax; an unconvincing best guess must not win."""
    best_project = FILE_PROJECT_NONE
    best_probability = 0.0
    shortlist = _shortlist(observation, catalog_entries, linear_projects)
    for index, (name, _description) in enumerate(shortlist):
        question_id = f"{CANDIDATE_QUESTION_PREFIX}{index}"
        if question_id not in answers_by_id:
            continue
        probability = answers.noul(answers_by_id, question_id)
        if probability > best_probability:
            best_probability = probability
            best_project = name
    if best_probability >= FILE_PROJECT_MATCH_THRESHOLD:
        return best_project, best_probability
    return FILE_PROJECT_NONE, best_probability


@dataclass(frozen=True, slots=True)
class _DispositionOutcome:
    disposition: str
    confidence: float
    reason: str
    needs_triage: bool = False
    needs_ticket: bool = False
    needs_redaction: bool = False


def _would_trash(flags: dict[str, float]) -> bool:
    return (
        flags[FILE_FLAG_BACKUP] >= FILE_FLAG_FLOORS["trash_backup"]
        and flags[FILE_FLAG_REGENERABLE] >= FILE_FLAG_FLOORS["trash_regenerable"]
    )


def _is_issue_list(flags: dict[str, float]) -> bool:
    return flags[FILE_FLAG_ISSUE_LIST] >= FILE_FLAG_FLOORS["issue_to_linear"]


def _is_evidence(flags: dict[str, float]) -> bool:
    return flags[FILE_FLAG_EVIDENCE] >= FILE_FLAG_FLOORS["evidence"]


def _movable_to_repo(project: str, kind: str, catalog_by_name: dict[str, dict[str, Any]]) -> bool:
    if project_kind(project) != FILE_PROJECT_KIND_REPO or kind not in FILE_KINDS_MOVABLE_TO_REPO:
        return False
    entry = catalog_by_name.get(project) or {}
    return bool(str(entry.get("local_path") or "").strip())


def _linear_sibling_for(project: str, linear_projects: list[dict[str, Any]]) -> str | None:
    """The Linear project this file's resolved project can attach evidence to or file
    an issue list into, if any -- `project` itself when it already is a Linear
    project, or the Linear project whose normalized name matches the repo's basename
    (design P4's attach rule: AgentMux -> agentmux, ZQ -> zq, Flight -> flight --
    mapped onto today's flat catalog instead of a persisted taxonomy). None means the
    resolved project (or "none"/a personal bucket) has no Linear home."""
    if project_kind(project) == FILE_PROJECT_KIND_LINEAR:
        return project
    if project_kind(project) != FILE_PROJECT_KIND_REPO:
        return None
    basename = _normalize_name(_repo_basename(project))
    for entry in linear_projects:
        name = str(entry.get("name") or "").strip()
        if name and _normalize_name(name) == basename:
            return f"linear:{name}"
    return None


def _resolve_disposition(
    flags: dict[str, float],
    project: str,
    project_probability: float,
    kind: str,
    catalog_by_name: dict[str, dict[str, Any]],
    linear_projects: list[dict[str, Any]],
) -> _DispositionOutcome:
    """Rules R1-R9 (design section 4.1), mapped onto today's flat project kinds
    (repo/linear/personal/none) rather than a taxonomy tree. The disposition is
    computed from the flag Nouls plus the already-resolved `project`/`kind`, never
    asked as a Choice -- the model can no longer be forced to guess a disposition
    before the project (and thus the legal dispositions) is known. First matching
    rule wins; R1 only forbids trash, it never picks a disposition itself.

    F1/F2 (Zach, 2026-09-23) replace the design's archive/move-to-repo defaults for
    evidence files and orphan issue lists with an explicit human/agent triage keep,
    and evidence for a project with a Linear home uploads there directly instead of
    being archived -- see FILE_DISPOSITION_ATTACH_EVIDENCE,
    REASON_FILE_EVIDENCE_NEEDS_TRIAGE, and REASON_FILE_ISSUE_NEEDS_TRIAGE.
    """
    private_guard = flags[FILE_FLAG_PRIVATE] >= FILE_FLAG_FLOORS["private_guard"]
    loss_record_guard = flags[FILE_FLAG_LOSS_RECORD] >= FILE_FLAG_FLOORS["loss_record"]
    if private_guard:
        reason = REASON_FILE_PRIVATE_GUARD
    elif loss_record_guard:
        reason = REASON_FILE_LOSS_RECORD_GUARD
    else:
        reason = REASON_SELECTED

    if not private_guard and not loss_record_guard and _would_trash(flags):
        confidence = min(
            flags[FILE_FLAG_BACKUP],
            flags[FILE_FLAG_REGENERABLE],
            1 - flags[FILE_FLAG_PRIVATE],
            1 - flags[FILE_FLAG_LOSS_RECORD],
        )
        return _DispositionOutcome(FILE_DISPOSITION_TRASH_CANDIDATE, confidence, REASON_SELECTED)

    if _is_issue_list(flags):
        if _linear_sibling_for(project, linear_projects) is not None:
            confidence = min(flags[FILE_FLAG_ISSUE_LIST], project_probability)
            return _DispositionOutcome(FILE_DISPOSITION_FILE_TO_LINEAR, confidence, reason)
        # F2: no Linear project to attach to -- queue for triage instead of guessing
        # a repo docs/ home for it.
        return _DispositionOutcome(
            FILE_DISPOSITION_KEEP,
            flags[FILE_FLAG_ISSUE_LIST],
            REASON_FILE_ISSUE_NEEDS_TRIAGE,
            needs_triage=True,
        )

    if _movable_to_repo(project, kind, catalog_by_name):
        return _DispositionOutcome(FILE_DISPOSITION_MOVE_TO_REPO, project_probability, reason)

    if project_kind(project) == FILE_PROJECT_KIND_PERSONAL:
        return _DispositionOutcome(FILE_DISPOSITION_PERSONAL_DOCS, project_probability, reason)

    if _is_evidence(flags):
        if _linear_sibling_for(project, linear_projects) is not None:
            # F1: evidence for a project with a Linear home uploads there directly --
            # the agent step still has to pick the exact issue, and a redacted copy
            # goes up instead of the raw file when private data was detected.
            return _DispositionOutcome(
                FILE_DISPOSITION_ATTACH_EVIDENCE,
                flags[FILE_FLAG_EVIDENCE],
                reason,
                needs_ticket=True,
                needs_redaction=private_guard,
            )
        return _DispositionOutcome(
            FILE_DISPOSITION_KEEP,
            flags[FILE_FLAG_EVIDENCE],
            REASON_FILE_EVIDENCE_NEEDS_TRIAGE,
            needs_triage=True,
        )

    if project_kind(project) != FILE_PROJECT_KIND_NONE:
        return _DispositionOutcome(FILE_DISPOSITION_ARCHIVE, project_probability, reason)

    return _DispositionOutcome(FILE_DISPOSITION_KEEP, 0.0, reason)


def decide(
    answers_by_id: dict[str, Any],
    observation: dict[str, Any],
    catalog_entries: list[dict[str, Any]],
    linear_projects: list[dict[str, Any]],
    *,
    project: str | None = None,
) -> FileResult:
    if project is None:
        project, project_probability = _resolve_project(
            answers_by_id, observation, catalog_entries, linear_projects
        )
    else:
        # A pre-decided project came from a deterministic strong match (design
        # section 2.3): the path is fully determined, implied edge probability 1.
        project_probability = STRONG_MATCH_PROBABILITY

    kind, _kind_confidence = answers.choice(answers_by_id, QUESTION_KIND)
    if kind not in FILE_KINDS:
        raise ValueError("TypeSafe file kind outside the closed set")
    flags = {flag_id: answers.noul(answers_by_id, flag_id) for flag_id in FILE_FLAGS}

    catalog_by_name = _catalog_by_name(catalog_entries)
    outcome = _resolve_disposition(
        flags, project, project_probability, kind, catalog_by_name, linear_projects
    )
    disposition, confidence, reason, needs_triage, needs_ticket, needs_redaction = (
        outcome.disposition,
        outcome.confidence,
        outcome.reason,
        outcome.needs_triage,
        outcome.needs_ticket,
        outcome.needs_redaction,
    )
    if disposition not in FILE_DISPOSITIONS:
        raise ValueError("computed file disposition outside the closed set")

    if disposition not in legal_dispositions_for(project):
        # Enforced in code as a safety net (typesafe-skills rule 8): the rule chain
        # above is designed so this can never fire, but an incoherent pair (e.g.
        # move-to-repo for a project that is not a repo) must never ship regardless.
        disposition, confidence, reason = (
            FILE_DISPOSITION_KEEP,
            0.0,
            REASON_FILE_ILLEGAL_DISPOSITION,
        )
        needs_triage = needs_ticket = needs_redaction = False
    elif confidence < FILE_DISPOSITION_CONFIDENCE_FLOORS[disposition]:
        # Gate by consequence, not a blanket min(): each disposition has its own bar.
        disposition, confidence, reason = (
            FILE_DISPOSITION_KEEP,
            0.0,
            REASON_BELOW_CONFIDENCE,
        )
        needs_triage = needs_ticket = needs_redaction = False

    destination = destination_hint_for(project, disposition, catalog_by_name)
    important = (
        flags[FILE_FLAG_PRIVATE] >= FILE_FLAG_FLOORS["private_guard"]
        or flags[FILE_FLAG_LOSS_RECORD] >= FILE_FLAG_FLOORS["loss_record"]
    )
    return FileResult(
        path=observation["path"],
        project=project,
        kind=kind,
        disposition=disposition,
        destination_hint=destination,
        confidence=confidence,
        reason=reason,
        needs_triage=needs_triage,
        needs_ticket=needs_ticket,
        needs_redaction=needs_redaction,
        important=important,
    )
