"""Language-agnostic file/function size checks for post-edit-lint.

Port of post-edit-lint.sh's file-structure section: a longer limit for test
files (table-driven tests are idiomatically longer), and a brace-based
heuristic for the longest function-like block in a brace/indent language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FILE_SIZE_LIMIT_DEFAULT = 250
FUNC_SIZE_LIMIT_DEFAULT = 50
FILE_SIZE_LIMIT_TEST = 500
FUNC_SIZE_LIMIT_TEST = 150

TEST_FILE_SUFFIXES = (
    "_test.go",
    ".test.ts",
    ".test.tsx",
    ".test.js",
    "_test.py",
    ".spec.ts",
    ".spec.js",
)
FUNC_HEURISTIC_EXTENSIONS = frozenset(
    {"go", "ts", "tsx", "js", "jsx", "swift", "php", "css", "scss", "java", "c", "cpp", "rs"}
)

_FUNC_OPEN_RE = re.compile(r"^(func |function |def |sub |class )")
_FUNC_CLOSE_RE = re.compile(r"^}")


@dataclass(frozen=True, slots=True)
class SizeLimits:
    file_lines: int
    func_lines: int

    @classmethod
    def for_file(cls, file_path: str) -> SizeLimits:
        if is_test_file(file_path):
            return cls(FILE_SIZE_LIMIT_TEST, FUNC_SIZE_LIMIT_TEST)
        return cls(FILE_SIZE_LIMIT_DEFAULT, FUNC_SIZE_LIMIT_DEFAULT)


def is_test_file(file_path: str) -> bool:
    return file_path.endswith(TEST_FILE_SUFFIXES)


def file_extension(file_path: str) -> str:
    return file_path.rsplit(".", 1)[-1] if "." in file_path else ""


def file_size_finding(file_path: str, line_count: int, limit: int) -> str | None:
    if line_count > limit:
        return f"FILE SIZE: {file_path} is {line_count} lines (limit: {limit}). Split this file into focused modules."
    return None


@dataclass(frozen=True, slots=True)
class LongestFunction:
    length: int
    start_line: int


def longest_function(lines: list[str]) -> LongestFunction | None:
    """Longest span between a function-like opener and a line starting with `}`."""
    best: LongestFunction | None = None
    start = 0
    for number, line in enumerate(lines, start=1):
        if start and _FUNC_CLOSE_RE.match(line):
            length = number - start
            if best is None or length > best.length:
                best = LongestFunction(length, start)
            start = 0
        elif _FUNC_OPEN_RE.match(line):
            start = number
    return best


def function_size_finding(extension: str, lines: list[str], limit: int) -> str | None:
    if extension not in FUNC_HEURISTIC_EXTENSIONS:
        return None
    longest = longest_function(lines)
    if longest is None or longest.length <= limit:
        return None
    return f"FUNCTION SIZE: Function at line {longest.start_line} is {longest.length} lines (limit: {limit}). Extract sub-functions."
