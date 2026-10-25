"""Word-splitting a Bash command the way orchestrator-only.sh does.

Three ported pieces, kept together because they form one pipeline (strip a
heredoc's body -> tokenize what's left -> split into the simple commands
between && || ; |):

- ``strip_heredoc_bodies``: a heredoc body is file CONTENT, not command
  arguments; every tokenizer here would otherwise flatten it into the
  token stream and inspect the file being written as though it were a
  list of paths and flags.
- ``tokenize``: quote-aware, matching ``xargs -n1``'s behavior (hc_tokenize)
  including its failure mode on unmatched quotes — callers fall back to a
  naive whitespace split, never a silent partial answer trusted as complete.
- ``split_into_groups``: the simple commands between control-operator
  tokens, matching split_into_groups' awk (spaced operators only — this is
  a known latent gap shared with the shell original, see MIGRATION note).
"""

from __future__ import annotations

import re
import shlex

HEREDOC_DELIM_PATTERNS = (
    re.compile(r'<<-?[ \t]*"([^"]+)"'),
    re.compile(r"<<-?[ \t]*'([^']+)'"),
    re.compile(r"<<-?[ \t]*([A-Za-z_][A-Za-z0-9_]*)"),
)
CONTROL_OPERATORS = frozenset({"&&", "||", ";", "|"})
REDIRECT_OPERATOR = re.compile(r"^([0-9]*>{1,2}|&>{1,2})")
REDIRECT_OPERATOR_ONLY = re.compile(r"^([0-9]*>{1,2}|&>{1,2})$")
FD_DUP = re.compile(r"^[0-9]>&[0-9]$")
DEVNULL_REDIRECT = re.compile(r"^([0-9]*>{1,2}|&>{1,2})/dev/null$")
DEV_NULL = "/dev/null"


def _heredoc_delimiter(line: str) -> str | None:
    for pattern in HEREDOC_DELIM_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group(1)
    return None


def strip_heredoc_bodies(command: str) -> str:
    """Drops heredoc body lines; keeps every command line (redirects and all)."""
    kept_lines: list[str] = []
    in_body = False
    delimiter = ""
    for line in command.split("\n"):
        if in_body:
            probe = line.lstrip("\t")
            if probe == delimiter or line == delimiter:
                in_body = False
            continue
        kept_lines.append(line)
        found = _heredoc_delimiter(line)
        if found is not None:
            delimiter = found
            in_body = True
    return "\n".join(kept_lines)


def tokenize(text: str) -> tuple[list[str], bool]:
    """Quote-aware split; ``ok`` is False on unmatched quoting (partial tokens kept)."""
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens: list[str] = []
    try:
        while True:
            token = lexer.get_token()
            if token is None:
                return tokens, True
            tokens.append(token)
    except ValueError:
        return tokens, False


def tokenize_with_fallback(text: str) -> list[str]:
    """The full pipeline callers use: tokenize, or a naive whitespace split
    when tokenizing fails or produces nothing."""
    tokens, ok = tokenize(text)
    if not ok or not tokens:
        return text.split()
    return tokens


def split_into_groups(tokens: list[str]) -> list[list[str]]:
    """The simple commands between && || ; | tokens, in order (may include an
    empty trailing group, matching the shell original)."""
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in CONTROL_OPERATORS:
            groups.append(current)
            current = []
        else:
            current.append(token)
    groups.append(current)
    return groups


TRAILING_CONTROL_CHARS = ";&|"


def _redirect_target(word: str) -> str:
    """The path a redirect word names, without an unspaced control operator
    glued to its end (``>/dev/null;`` or ``>out.txt&&`` tokenize as one word)."""
    return word.rstrip(TRAILING_CONTROL_CHARS)


def redirect_targets(tokens: list[str]) -> list[str]:
    """One write-redirect target per output line, skipping fd-dups and /dev/null."""
    targets: list[str] = []
    count = len(tokens)
    for index, token in enumerate(tokens):
        if FD_DUP.match(token) or DEVNULL_REDIRECT.match(_redirect_target(token)):
            continue
        if REDIRECT_OPERATOR_ONLY.match(token):
            following = _redirect_target(tokens[index + 1]) if index + 1 < count else ""
            if following and following != DEV_NULL:
                targets.append(following)
            continue
        match = REDIRECT_OPERATOR.match(token)
        if match:
            target = _redirect_target(token[match.end() :])
            if target:
                targets.append(target)
    return targets
