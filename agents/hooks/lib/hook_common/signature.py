"""How hooks key their history: a command's signature and a content digest.

Ports of hook-common.sh's hc_command_signature and hc_sha256. One
normalization shared by the recorder (bash-signature-record) and every
reader (two-strikes-gate, completion-gate) makes "same command" an exact
string match.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping

ASSIGNMENT_WORD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SIGNATURE_WORD_COUNT = 3
SHA256_OVERRIDE_ENV = "HC_SHA256_OVERRIDE"

# A leading `set -euo pipefail`-style line: shell boilerplate every script
# carries, never the distinguishing part of the command.
LEADING_SET_LINE = re.compile(r"^set\s+\S.*?(?:\n|$)")
# A leading `cd <dir> &&` / `cd <dir>;` prefix: navigation, not the command.
LEADING_CD_PREFIX = re.compile(r"^cd\s+\S+\s*(?:&&|;)\s*")


def _strip_shell_preamble(text: str) -> str:
    """Drop a leading `set ...` line and/or `cd <dir> &&` prefix.

    These are shared boilerplate, not the command itself — leaving them in
    made unrelated commands that both start with `set -euo pipefail` collide
    on signature.
    """
    stripped = text.lstrip()
    match = LEADING_SET_LINE.match(stripped)
    if match:
        stripped = stripped[match.end() :].lstrip()
    match = LEADING_CD_PREFIX.match(stripped)
    if match:
        stripped = stripped[match.end() :].lstrip()
    return stripped


def command_signature(text: str) -> str:
    """The first 3 whitespace words that aren't ``NAME=value`` assignments, space-joined.

    Shell preamble (a leading `set ...` line, a leading `cd <dir> &&`
    prefix) is stripped first so two commands that only share boilerplate
    don't collide on signature.
    """
    text = _strip_shell_preamble(text)
    words: list[str] = []
    for word in text.split():
        if ASSIGNMENT_WORD.match(word):
            continue
        words.append(word)
        if len(words) >= SIGNATURE_WORD_COUNT:
            break
    return " ".join(words)


def sha256_digest(text: str, env: Mapping[str, str] = os.environ) -> str:
    """sha256 hex digest, or HC_SHA256_OVERRIDE when a test pins one."""
    override = env.get(SHA256_OVERRIDE_ENV)
    if override:
        return override
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()
