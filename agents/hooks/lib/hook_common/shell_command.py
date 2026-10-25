"""A Bash-tool command split into shell words."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

# Characters that make up a shell control operator (&&, ||, ;, |, &, (, )).
# A word built only from these separates two commands; a word containing
# < or > is a redirection instead and stays inside its command.
CONTROL_OPERATOR_CHARS = frozenset(";&|()")


def is_control_operator(word: str) -> bool:
    return bool(word) and set(word) <= CONTROL_OPERATOR_CHARS


@dataclass(frozen=True, slots=True)
class ShellCommand:
    """A Bash-tool command split into shell words, quotes removed.

    Word equality is the discriminator every Bash hook needs: a quoted flag
    is still a live flag (``git commit "--no-verify"`` yields a standalone
    ``--no-verify`` word), while a trigger phrase inside a quoted sentence
    stays fused into one word that never equals a flag. Operators are their
    own words even when glued (``a;b`` -> ``a ; b``). ``$(...)`` is split
    into ``$ ( ... )``; backticks are NOT understood — hooks that must see
    through command substitution need a second, text-level check.
    """

    words: tuple[str, ...]

    @classmethod
    def parse(cls, text: str) -> ShellCommand | None:
        """None when the quoting is unparseable (e.g. an unmatched quote).

        Callers must treat None as "unusual input" and take their stricter
        path, never as "no words".
        """
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        try:
            return cls(tuple(lexer))
        except ValueError:
            return None

    def segments(self) -> tuple[tuple[str, ...], ...]:
        """The simple commands between control operators, in order, non-empty."""
        found: list[tuple[str, ...]] = []
        current: list[str] = []
        for word in self.words:
            if not is_control_operator(word):
                current.append(word)
                continue
            if current:
                found.append(tuple(current))
            current = []
        if current:
            found.append(tuple(current))
        return tuple(found)
