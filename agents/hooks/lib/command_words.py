"""The simple commands a Bash string will run, each as its argv.

Sees through what an agent actually types: control operators with or
without spaces (``a&&b``, ``a;b``, newlines), subshells and ``$(...)``,
leading ``VAR=value`` assignments, transparent wrappers (``env``,
``command``, ``exec``, ``sudo``, ``nohup``, ``time``), and nested
``bash -c '...'`` strings. Quoted text stays one word, so a commit
message or ``echo`` argument that mentions a command is never mistaken
for running it, and heredoc bodies are file content, not commands.
"""

from __future__ import annotations

import os
import re
import shlex

from orchestrator_only_shell_words import strip_heredoc_bodies

SEPARATOR_CHARS = "();&|\n"
WHITESPACE = " \t\r"
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECTION = re.compile(r"^[0-9]*(>>?|<)")
FD_DUPLICATION = re.compile(r"[0-9]*>&[0-9-]+")
COMBINED_REDIRECTION = re.compile(r"&>(>?)")
TRANSPARENT_WRAPPERS = frozenset({"command", "exec", "nohup", "time", "sudo", "env"})
NESTED_SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
MAX_NESTING = 3


def _words(text: str) -> list[str] | None:
    """Quote-aware words with each run of separator chars as its own word;
    None when the quoting is unbalanced."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=SEPARATOR_CHARS)
    lexer.whitespace = WHITESPACE
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _is_separator(word: str) -> bool:
    return bool(word) and all(char in SEPARATOR_CHARS for char in word)


def _segments(words: list[str]) -> list[list[str]]:
    """Splits on separators and drops redirections (``2>/dev/null``, ``> out``)."""
    segments: list[list[str]] = [[]]
    skip_target = False
    for word in words:
        if skip_target and not _is_separator(word):
            skip_target = False
        elif _is_separator(word):
            skip_target = False
            segments.append([])
        elif match := REDIRECTION.match(word):
            skip_target = match.end() == len(word)
        else:
            segments[-1].append(word)
    return [segment for segment in segments if segment]


def _strip_prefix(argv: list[str]) -> list[str]:
    """Drops leading assignments and transparent wrappers (and their flags)."""
    index = 0
    total = len(argv)
    while index < total:
        word = argv[index]
        if ASSIGNMENT.match(word):
            index += 1
        elif os.path.basename(word) in TRANSPARENT_WRAPPERS:
            index += 1
            while index < total and argv[index].startswith("-"):
                index += 1
        else:
            break
    return argv[index:]


def _nested_script(argv: list[str]) -> str | None:
    """The script of ``bash -c '<script>'`` (also ``-lc``, ``-ec``), else None."""
    if not argv or os.path.basename(argv[0]) not in NESTED_SHELLS:
        return None
    for index, word in enumerate(argv[1:-1], start=1):
        if word.startswith("-") and not word.startswith("--") and "c" in word:
            return argv[index + 1]
    return None


def simple_commands(command: str, depth: int = 0) -> list[list[str]]:
    """Each simple command's argv, program first, in order of appearance."""
    inspectable = strip_heredoc_bodies(command)
    inspectable = FD_DUPLICATION.sub(" ", inspectable)
    inspectable = COMBINED_REDIRECTION.sub(r" >\1", inspectable)
    words = _words(inspectable)
    if words is None:
        words = command.split()
    commands: list[list[str]] = []
    for segment in _segments(words):
        argv = _strip_prefix(segment)
        if not argv:
            continue
        script = _nested_script(argv)
        if script is not None and depth < MAX_NESTING:
            commands.extend(simple_commands(script, depth + 1))
        else:
            commands.append(argv)
    return commands
