"""Destination-argument extraction for layout-guard's Bash matcher.

Every extractor reads a TOKEN STREAM (shell words with quotes already
stripped), never the raw command text — that is what fixes the false
positive where a quoted sentence merely mentioning a forbidden path or a
redirection operator is mistaken for one.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Sequence

GIT_CLONE_VALUE_FLAGS = frozenset(
    {
        "-b",
        "-B",
        "-o",
        "--origin",
        "--branch",
        "--depth",
        "--reference",
        "--reference-if-able",
        "--template",
        "--separate-git-dir",
        "-c",
        "--config",
    }
)
GIT_WORKTREE_ADD_VALUE_FLAGS = frozenset({"-b", "-B", "--reason", "--orphan"})

SHELL_CONTROL_OPERATORS = frozenset({"&&", "||", ";", "|", "&", ";;", "|&"})

_HEREDOC_DELIM_RE = re.compile(r'<<-?\s*(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z_][A-Za-z0-9_]*))')
_FD_REDIRECT_RE = re.compile(r"^(?:[0-9]+)?>{1,2}$")


def tokenize(command: str) -> list[str] | None:
    """Shell-word-splits ``command``; None when the quoting is unparseable (parity with hc_tokenize)."""
    lexer = shlex.shlex(_unquoted_newlines_as_separators(command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _unquoted_newlines_as_separators(command: str) -> str:
    """Rewrites newlines outside quotes to ``;`` so they survive word splitting as separators."""
    out: list[str] = []
    quote = ""
    for char in command:
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "\n":
            char = " ; "
        out.append(char)
    return "".join(out)


def command_segments(words: Sequence[str]) -> list[list[str]]:
    """Splits a token stream at shell control operators into one word list per command."""
    segments: list[list[str]] = [[]]
    for word in words:
        if word in SHELL_CONTROL_OPERATORS:
            segments.append([])
        else:
            segments[-1].append(word)
    return [segment for segment in segments if segment]


def legacy_whitespace_tokenize(command: str) -> list[str]:
    """Naive whitespace-only split, used only when tokenize() fails to parse the quoting."""
    return command.split()


def strip_heredoc_bodies(command: str) -> str:
    """Drops heredoc BODY lines (file content), keeping the command line that opens them."""
    kept: list[str] = []
    in_body = False
    delimiter = ""
    for line in command.split("\n"):
        if in_body:
            probe = line.lstrip("\t")
            if probe == delimiter or line == delimiter:
                in_body = False
            continue
        kept.append(line)
        match = _HEREDOC_DELIM_RE.search(line)
        if match:
            delimiter = next(group for group in match.groups() if group is not None)
            in_body = True
    return "\n".join(kept)


def _extract_after(
    words: Sequence[str], start_index: int, value_flags: frozenset[str], want_index: int | None
) -> str | None:
    """First (or want_index-th) non-flag word after ``start_index``, skipping value flags."""
    skip_next = False
    count = 0
    for word in words[start_index:]:
        if skip_next:
            skip_next = False
            continue
        if word in value_flags:
            skip_next = True
            continue
        if word.startswith("-"):
            continue
        count += 1
        if want_index is None or count == want_index:
            return word
    return None


def worktree_add_destination(words: Sequence[str]) -> str | None:
    for segment in command_segments(words):
        for i in range(len(segment) - 1):
            if segment[i] == "worktree" and segment[i + 1] == "add":
                return _extract_after(segment, i + 2, GIT_WORKTREE_ADD_VALUE_FLAGS, want_index=1)
    return None


def git_subcommand_destination(
    words: Sequence[str], subcommand: str, want_index: int
) -> str | None:
    for segment in command_segments(words):
        for i in range(len(segment) - 1):
            if segment[i] == "git" and segment[i + 1] == subcommand:
                return _extract_after(segment, i + 2, GIT_CLONE_VALUE_FLAGS, want_index)
    return None


def mkdir_targets(words: Sequence[str]) -> list[str]:
    targets: list[str] = []
    for segment in command_segments(words):
        for i, word in enumerate(segment):
            if word == "mkdir":
                targets += [w for w in segment[i + 1 :] if not w.startswith("-")]
                break
    return targets


def last_positional_after(words: Sequence[str], command_name: str) -> str | None:
    target = None
    for segment in command_segments(words):
        for i, word in enumerate(segment):
            if word == command_name:
                target = next(
                    (w for w in reversed(segment[i + 1 :]) if not w.startswith("-")), target
                )
                break
    return target


def redirection_targets(words: Sequence[str]) -> list[str]:
    """The path after a ``>``/``>>`` (optionally fd-prefixed) that is its OWN word."""
    targets = []
    for i, word in enumerate(words):
        if (word in (">", ">>") or _FD_REDIRECT_RE.match(word)) and i + 1 < len(words):
            targets.append(words[i + 1])
    return targets


def non_empty(values: Iterable[str | None]) -> list[str]:
    return [value for value in values if value]
