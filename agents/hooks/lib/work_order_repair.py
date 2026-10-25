"""Repair-by-reference: a denied work order is stored under an order_ref so
the caller resends only the missing or corrected fragment, never the whole
prompt. See work-order-gate.sh's header for the protocol.

A resend is ``order_ref: <sha>`` on line one, then either the missing
```yaml fence (the stored prompt had none) or a ```work_order_patch block.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hook_common import file_mtime

# A stored-but-unrepaired prompt older than this is treated as unknown
# rather than silently repaired forever — 24h.
PENDING_MAX_AGE_SECS = 86400
PENDING_DIR_NAME = "pending"
EXAMPLES_DIR_NAME = "examples"
PENDING_SUFFIX = ".txt"

ORDER_REF_LINE_PATTERN = re.compile(r"^order_ref: ([0-9a-f]{64})\s*$")
MAIN_FENCE_PATTERN = re.compile(r"```yaml\s*$", re.MULTILINE)
PATCH_FENCE_OPEN = re.compile(r"^```work_order_patch\s*$")
PATCH_FENCE_CLOSE = re.compile(r"^```\s*$")


def order_ref_of(prompt: str) -> str:
    """The repair key: sha256 of the prompt the caller must later echo back.

    Not hook_common.sha256_digest: the .sh hashes with shasum directly, so
    HC_SHA256_OVERRIDE never applies here.
    """
    return hashlib.sha256(prompt.encode("utf-8", errors="surrogateescape")).hexdigest()


def resend_order_ref(prompt: str) -> str | None:
    """The order_ref a resend names on its first line, if it is one."""
    match = ORDER_REF_LINE_PATTERN.match(prompt.split("\n", 1)[0])
    return match.group(1) if match else None


def has_main_fence(text: str) -> bool:
    return bool(MAIN_FENCE_PATTERN.search(text))


def strip_patch_fences(text: str) -> str:
    """Drops every ```work_order_patch block, so only the latest patch applies.

    The compiler applies the FIRST patch fence it finds; leaving an earlier,
    already-rejected patch in place would replay it forever.
    """
    kept: list[str] = []
    in_patch = False
    for line in text.split("\n"):
        if not in_patch and PATCH_FENCE_OPEN.match(line):
            in_patch = True
        elif in_patch and PATCH_FENCE_CLOSE.match(line):
            in_patch = False
        elif not in_patch:
            kept.append(line)
    return "\n".join(kept)


def resend_body(prompt: str) -> str:
    """Everything after the order_ref line, minus one blank line left for readability.

    Trailing newlines are dropped, as the .sh's ``$(...)`` capture drops them.
    """
    rest = prompt.split("\n")[1:]
    if rest and rest[0] == "":
        rest = rest[1:]
    return "\n".join(rest).rstrip("\n")


def merge_resend(stored: str, body: str) -> str:
    """The prompt the resend means: the fence prepended, or the patch appended."""
    if has_main_fence(body) and not has_main_fence(stored):
        return f"{body}\n{stored}"
    unpatched = strip_patch_fences(stored).rstrip("\n")
    return f"{unpatched}\n{body}"


class PendingState(Enum):
    FOUND = "found"
    UNKNOWN = "unknown"  # never stored, or already resolved
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class PendingLookup:
    state: PendingState
    prompt: str = ""


@dataclass(frozen=True, slots=True)
class PendingOrders:
    """Denied prompts awaiting repair, one file per order_ref."""

    orders_dir: Path

    @property
    def directory(self) -> Path:
        return self.orders_dir / PENDING_DIR_NAME

    def _path(self, ref: str) -> Path:
        return self.directory / f"{ref}{PENDING_SUFFIX}"

    def store(self, ref: str, prompt: str) -> None:
        with contextlib.suppress(OSError):
            self.directory.mkdir(parents=True, exist_ok=True)
            self._path(ref).write_text(prompt)

    @property
    def examples_directory(self) -> Path:
        return self.orders_dir / EXAMPLES_DIR_NAME

    def example_path(self, ref: str) -> Path:
        return self.examples_directory / f"{ref}{PENDING_SUFFIX}"

    def discard(self, ref: str) -> None:
        for path in (self._path(ref), self.example_path(ref)):
            with contextlib.suppress(OSError):
                path.unlink()

    def lookup(self, ref: str, now_epoch: float) -> PendingLookup:
        """The stored prompt; an expired one is discarded on the way out."""
        path = self._path(ref)
        if not path.is_file():
            return PendingLookup(PendingState.UNKNOWN)
        mtime = file_mtime(path) or 0
        if mtime == 0 or int(now_epoch) - mtime > PENDING_MAX_AGE_SECS:
            self.discard(ref)
            return PendingLookup(PendingState.EXPIRED)
        # rstrip: the .sh reads it through ``$(cat ...)``, which drops trailing newlines.
        return PendingLookup(PendingState.FOUND, path.read_text().rstrip("\n"))
