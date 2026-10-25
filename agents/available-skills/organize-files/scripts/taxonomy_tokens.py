"""Tokenizing and document-frequency helpers shared by the taxonomy build rules.

Mirrors the tokenizer conventions in typesafe-ai/scripts/classify_file.py
(_words, FILE_GENERIC_SCORING_STOPWORDS) but is a standalone copy: the builder
must not import across skill boundaries, and this module has no other
dependents.
"""

from __future__ import annotations

import re

MIN_TOKEN_LENGTH = 3

# Descriptor words that appear across many repos/descriptions and carry no
# project-identifying signal on their own.
GENERIC_STOPWORDS = frozenset(
    {
        "the", "a", "an", "for", "and", "or", "to", "of", "in", "on", "is",
        "it", "this", "that", "with", "from", "live", "test", "tests",
        "testing", "proof", "demo", "data", "file", "files", "new", "old",
        "final", "draft", "notes", "note", "plan", "review", "docs", "doc",
        "report", "summary", "copy", "backup", "output", "input", "log",
        "logs", "list", "misc", "temp", "tmp", "repo", "repository", "app",
        "system", "tool", "tools", "service", "project", "site", "status",
        "saas", "platform",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def words(text: str) -> set[str]:
    """Tokenize into scoring-length words, excluding generic stopwords."""
    return {
        raw
        for raw in _WORD_RE.findall(text.lower())
        if len(raw) >= MIN_TOKEN_LENGTH and raw not in GENERIC_STOPWORDS
    }


def normalize_keyword(keyword: str) -> str:
    return str(keyword).strip().lower()


def repo_basename(full_name: str) -> str:
    return full_name.rsplit("/", 1)[-1].lower()


def document_frequency(token_sets: list[set[str]]) -> dict[str, int]:
    """How many members of `token_sets` contain each token."""
    frequency: dict[str, int] = {}
    for tokens in token_sets:
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1
    return frequency
