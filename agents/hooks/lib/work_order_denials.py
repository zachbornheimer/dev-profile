"""The reasons work-order-gate denies with — compact JSON a caller can act on.

Key order is load-bearing: Grok truncates deny reasons from the END at
~1KB (session 01a0babe lost the repair path when order_ref sat after a
long example). The fields a caller needs come first, and they stay small.

The fence itself is not in the JSON. An inlined work_order scaffold is
what truncation drops, and it reads as a whole new order. The file at
example_path is only the missing piece: a ```work_order_patch for the
missing field, or a key skeleton when the prompt had no fence. The stored
prompt stays behind order_ref. The retry is that line plus the file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from work_order_repair import PENDING_SUFFIX, has_main_fence, order_ref_of

# Grok keeps about the first 1KB of a deny reason and drops the rest.
TRUNCATION_BUDGET = 1024

REQUIRED_FIELDS = (
    "schema_version",
    "intent",
    "scope.primary_targets",
    "scope.allowed_writes",
    "acceptance",
)

POLICY_CODE_PREFIX = "policy."

STALE_UNKNOWN = "unknown"
STALE_EXPIRED = "expired"

_REQUIRED_PROPERTY = re.compile(r"'([^']+)' is a required property")
_PLACEHOLDER_PATH = "path/to/file"
_PLACEHOLDER_INTENT = "Outcome already stated in the stored prompt."
_PLACEHOLDER_RUN = "echo hi"
_ACCEPTANCE_VALUE = [
    {
        "id": "t",
        "kind": "command",
        "run": _PLACEHOLDER_RUN,
        "expect": {"exit_code": 0},
    }
]
_SCOPE_VALUE = {
    "primary_targets": [_PLACEHOLDER_PATH],
    "allowed_writes": [_PLACEHOLDER_PATH],
}
_VALUES: dict[str, Any] = {
    "schema_version": 1,
    "intent": _PLACEHOLDER_INTENT,
    "scope": _SCOPE_VALUE,
    "scope.primary_targets": [_PLACEHOLDER_PATH],
    "scope.allowed_writes": [_PLACEHOLDER_PATH],
    "acceptance": _ACCEPTANCE_VALUE,
    "acceptance.id": "t",
    "acceptance.kind": "command",
    "acceptance.run": _PLACEHOLDER_RUN,
    "acceptance.expect": {"exit_code": 0},
}


@dataclass(frozen=True, slots=True)
class FieldGap:
    """One schema miss: the key the caller sees, and the pointer a patch uses."""

    name: str
    pointer: str
    code: str


def _compact(body: Mapping[str, Any]) -> str:
    """``jq -c`` formatting."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def _display_name(pointer: str) -> str:
    parts = [
        part
        for part in pointer.split("/")
        if part and part != "work_order" and not part.isdigit()
    ]
    return ".".join(parts)


def fields_from_errors(errors: Sequence[Mapping[str, Any]]) -> list[FieldGap]:
    """Key names only. Messages stay out of the deny JSON."""
    gaps: list[FieldGap] = []
    seen: set[str] = set()
    for error in errors:
        path = str(error.get("path") or "")
        code = str(error.get("code") or "")
        if code == "missing_fence":
            continue
        pointer = path if path.startswith("/") else f"/{path}"
        if code == "required":
            match = _REQUIRED_PROPERTY.search(str(error.get("message") or ""))
            if match:
                pointer = pointer.rstrip("/") + "/" + match.group(1)
        name = _display_name(pointer) or "work_order"
        if pointer in seen:
            continue
        seen.add(pointer)
        gaps.append(FieldGap(name=name, pointer=pointer, code=code))
    return gaps


def policy_errors(errors: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Errors where the order is well-formed but breaks a rule no patch can fix."""
    return [
        error
        for error in errors
        if str(error.get("code") or "").startswith(POLICY_CODE_PREFIX)
    ]


def missing_names(errors: Sequence[Mapping[str, Any]]) -> list[str]:
    if any(str(error.get("code") or "") == "missing_fence" for error in errors):
        return list(REQUIRED_FIELDS)
    names: list[str] = []
    for gap in fields_from_errors(errors):
        if gap.name not in names:
            names.append(gap.name)
    return names


def _missing_key_fence(missing: Sequence[str]) -> str:
    """The fence's keys, with no placeholder prose and no dummy paths."""
    wanted = set(missing)
    lines = ["```yaml", "work_order:"]
    if "schema_version" in wanted:
        lines.append("  schema_version: 1")
    if "intent" in wanted:
        lines.append("  intent:")
    scope_children = [
        name.removeprefix("scope.")
        for name in ("scope.primary_targets", "scope.allowed_writes")
        if name in wanted
    ]
    if "scope" in wanted or scope_children:
        lines.append("  scope:")
        if "scope" in wanted and not scope_children:
            scope_children = ["primary_targets", "allowed_writes"]
        for child in scope_children:
            lines.append(f"    {child}:")
    if "acceptance" in wanted:
        lines.append("  acceptance:")
    lines.append("```")
    return "\n".join(lines) + "\n"


def _patch_fence(gaps: Sequence[FieldGap]) -> str:
    ops = [
        {
            "op": "add" if gap.code == "required" else "replace",
            "path": gap.pointer,
            "value": _VALUES[gap.name],
        }
        for gap in gaps
    ]
    body = json.dumps(ops, separators=(",", ":"))
    return f"```work_order_patch\n{body}\n```\n"


def example_fragment(
    *,
    has_fence: bool,
    missing: Sequence[str],
    errors: Sequence[Mapping[str, Any]],
) -> str:
    """What the caller pastes after the order_ref line. Never a full order."""
    if not has_fence:
        return _missing_key_fence(missing)
    gaps = fields_from_errors(errors)
    order_gaps = [gap for gap in gaps if gap.pointer.startswith("/work_order")]
    if order_gaps and all(gap.name in _VALUES for gap in order_gaps):
        return _patch_fence(order_gaps)
    if len(missing) == 1:
        return missing[0] + "\n"
    return "".join(f"{name}\n" for name in missing)


def unparsed_fragment(errors: Sequence[Mapping[str, Any]]) -> str:
    """The parse error, which can be long. It is not a work_order scaffold."""
    lines = [
        f"{error.get('path', '')} {error.get('code', '')}: {error.get('message', '')}"
        for error in errors
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def write_example(directory: Path, ref: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ref}{PENDING_SUFFIX}"
    path.write_text(text)
    return path


def repair_payload(ref: str, missing: Sequence[str], example_path: str) -> str:
    """order_ref first, then key names, then the path. Nothing else."""
    return _compact(
        {
            "order_ref": ref,
            "missing": list(missing),
            "example_path": example_path,
        }
    )


def repairable_reason(
    ref: str,
    prompt: str,
    extra: Mapping[str, Any],
    examples_dir: Path,
) -> str:
    errors = [item for item in extra.get("errors") or [] if isinstance(item, Mapping)]
    missing = list(extra["missing"]) if "missing" in extra else missing_names(errors)
    if not missing and not has_main_fence(prompt):
        missing = list(REQUIRED_FIELDS)
    text = example_fragment(
        has_fence=has_main_fence(prompt),
        missing=missing,
        errors=errors,
    )
    path = write_example(examples_dir, ref, text)
    return repair_payload(ref, missing, str(path))


def missing_fence_fields() -> dict[str, Any]:
    return {"missing": list(REQUIRED_FIELDS)}


def stale_ref_reason(ref: str, kind: str, examples_dir: Path) -> str:
    """The resend named an order_ref the gate can't repair from.

    ``kind`` is ``unknown`` or ``expired``. That word is the file, not a scaffold.
    """
    path = write_example(examples_dir, ref, kind + "\n")
    return repair_payload(ref, ["work_order"], str(path))


def fresh_order_reason(
    prompt: str,
    extra: Mapping[str, Any],
    examples_dir: Path,
) -> str:
    """The YAML didn't parse, so no patch can apply and nothing is stored.

    No order_ref: a repair merge would replay the broken fence. The long
    parser text goes in the file.
    """
    errors = [item for item in extra.get("errors") or [] if isinstance(item, Mapping)]
    missing = missing_names(errors) or ["work_order"]
    path = write_example(examples_dir, order_ref_of(prompt), unparsed_fragment(errors))
    return _compact({"missing": missing, "example_path": str(path)})


def policy_reason(errors: Sequence[Mapping[str, Any]]) -> str:
    """A rule the order breaks: code first, then the message written for the caller.

    Unlike a schema gap, nothing is missing and nothing is stored. The fix is
    a different order, so there is no order_ref and no example file.
    """
    return _compact(
        {
            "policy": [
                {"code": error.get("code", ""), "message": error.get("message", "")}
                for error in policy_errors(errors)
            ]
        }
    )
