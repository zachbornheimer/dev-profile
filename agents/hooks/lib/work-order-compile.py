#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.20", "pyyaml>=6.0", "jsonpatch>=1.33"]
# ///
"""Compile-and-validate step for the structured work-order protocol.

Owner's governing rule (skills/prompt-writer/references/work-order-protocol.md):
models propose semantic intent; deterministic code supplies syntax, defaults,
execution policy, validation, and verification. This script is that
deterministic code — work-order-gate.sh (PreToolUse) is the only caller.

Two entry points:

  * `work-order-compile.py compile` — reads a JSON envelope on stdin (see
    `_read_envelope`), extracts the ```yaml work_order fence (and an optional
    ```work_order_patch fence) from `prompt`, validates it, checks the
    path-safety policy, compiles the execution block from call params +
    defaults, and prints ONE JSON object to stdout:
      - success: {"ok": true, "work_order": {...}, "execution": {...},
                  "order_id": "<sha256 hex>", "warnings": [...]}
      - failure: {"ok": false, "errors": [{"path", "code", "message"}, ...]}
        plus "repairable": false when a work_order_patch cannot apply
        (the fenced YAML did not parse).
    Never raises for a malformed order — every expected failure mode becomes
    an entry in "errors". An unexpected exception is allowed to propagate
    (non-JSON on stdout, non-zero exit) so the calling hook's fail-open
    behavior (bad output -> allow) is the safety net, not a caught-and-hidden
    bug here.

  * `work-order-compile.py lint-schema <path>` — checks one JSON Schema file
    for duplicate object keys (which `json.load` would otherwise silently
    resolve to "last key wins"). Prints {"ok": true} or
    {"ok": false, "errors": [...]}. Exists standalone so the test suite can
    point it at a deliberately-broken fixture schema without touching the
    real one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonpatch
import yaml
from jsonschema import Draft202012Validator

SELF_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SELF_DIR.parent
SCHEMA_PATH = HOOKS_DIR / "schemas" / "work-order.schema.json"
DEFAULTS_PATH = HOOKS_DIR / "schemas" / "work-order-defaults.json"

# A target is exempt from the worktree-isolation requirement when it resolves
# under one of these roots — config/skill trees this harness itself owns, not
# a repo a subagent could corrupt shared state in.
EXEMPT_ROOTS = ("~/.agents", "~/.claude")
GIT_TIMEOUT_SECS = 5

MAIN_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)
PATCH_FENCE_RE = re.compile(r"```work_order_patch\s*\n(.*?)```", re.DOTALL)

TURN_CAP_PROSE_RE = re.compile(r"turn cap:\s*(\d+)", re.IGNORECASE)
TOKEN_BUDGET_PROSE_RE = re.compile(r"token budget:\s*~?\s*(\d+(?:\.\d+)?)\s*(k)?", re.IGNORECASE)

# Implement workers already have the compiled order plus the code-approval
# brief. Path-reading these skills every spawn was 145+102 sessions in the
# 14-day audit (ZYS-804). Drop them from compiled required_inputs unless
# the spawn is editing those files.
BANNED_IMPLEMENT_SKILL_READS = (
    "prompt-writer/SKILL.md",
    "code-construction/SKILL.md",
)
DO_NOT_PATH_READ_SKILLS_COMMENT = (
    "# Do not Read prompt-writer/SKILL.md or code-construction/SKILL.md "
    "unless this spawn is editing those files. testing-practices may load "
    "when the order edits tests.\n"
)
STANDING_OBJECTIVE_COMMENT = (
    "# objective: ship the acceptance with the least wall-clock time and "
    "tokens. Read required_inputs first; reuse scope.given as-is; do no "
    "research, capture, or extra proof beyond what acceptance needs.\n"
)


class DuplicateKeyError(ValueError):
    """Raised by `_no_duplicate_keys` when a JSON/YAML mapping repeats a key."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateKeyError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


class _DuplicateKeySafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects a mapping which repeats a key, mirroring the
    JSON `object_pairs_hook` duplicate check for the YAML work-order fence
    itself (PyYAML's default behavior is "last key wins", identical to
    json.load's default)."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode):
    loader.flatten_mapping(node)
    pairs = loader.construct_pairs(node)
    return _no_duplicate_keys(pairs)


_DuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def lint_schema_no_duplicate_keys(path: Path) -> list[str]:
    """Returns a list of error strings (empty = clean) for duplicate keys
    anywhere in the schema's JSON object tree."""
    try:
        raw = path.read_text()
    except OSError as exc:
        return [f"cannot read schema {path}: {exc}"]
    errors: list[str] = []

    def hook(pairs: list[tuple[str, object]]) -> dict:
        seen: set[str] = set()
        for key, _value in pairs:
            if key in seen:
                errors.append(f"duplicate key {key!r} in {path}")
            seen.add(key)
        return dict(pairs)

    try:
        json.loads(raw, object_pairs_hook=hook)
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: {exc}")
    return errors


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def _extract_fence(pattern: re.Pattern, prompt: str) -> str | None:
    match = pattern.search(prompt)
    return match.group(1) if match else None


def _parse_yaml_order(text: str) -> tuple[dict | None, list[dict]]:
    try:
        parsed = yaml.load(text, Loader=_DuplicateKeySafeLoader)
    except DuplicateKeyError as exc:
        return None, [_err("/work_order", "duplicate_key", str(exc))]
    except yaml.YAMLError as exc:
        return None, [_err("/work_order", "yaml_parse_error", str(exc))]
    if not isinstance(parsed, dict):
        return None, [_err("/work_order", "type", "fenced block did not parse to a YAML mapping")]
    return parsed, []


def _apply_patch(order: dict, patch_text: str) -> tuple[dict | None, list[dict]]:
    try:
        patch_ops = json.loads(patch_text)
    except json.JSONDecodeError as exc:
        return None, [_err("/work_order_patch", "json_parse_error", str(exc))]
    if not isinstance(patch_ops, list):
        return None, [
            _err(
                "/work_order_patch",
                "type",
                "work_order_patch must be a JSON Patch array (RFC 6902)",
            )
        ]
    try:
        patched = jsonpatch.apply_patch(order, patch_ops, in_place=False)
    except jsonpatch.JsonPatchException as exc:
        return None, [_err("/work_order_patch", "patch_apply_error", str(exc))]
    if not isinstance(patched, dict):
        return None, [_err("/work_order_patch", "type", "patched result is not a JSON object")]
    return patched, []


def _validate_against_schema(order: dict) -> list[dict]:
    with SCHEMA_PATH.open() as fh:
        schema = json.load(fh)
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(order), key=lambda e: list(e.absolute_path)):
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        errors.append(_err(path, error.validator, error.message))
    return errors


def _resolve_path(raw: str, cwd: str) -> str:
    expanded = os.path.expanduser(raw)
    absolute = expanded if os.path.isabs(expanded) else os.path.join(cwd, expanded)
    return os.path.realpath(os.path.normpath(absolute))


def _normalize_path(raw: str, cwd: str) -> str:
    return _resolve_path(raw, cwd).lower()


def _nearest_existing_dir(path: str) -> str:
    candidate = path
    while candidate and not os.path.isdir(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            return ""
        candidate = parent
    return candidate


def _git_output(check_dir: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", check_dir, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _is_repo_path(resolved: str) -> bool:
    check_dir = _nearest_existing_dir(resolved)
    return bool(check_dir) and _git_output(check_dir, "rev-parse") is not None


def _main_repo_root(resolved: str) -> str | None:
    """Main working tree of the repo holding `resolved`. A linked worktree
    (e.g. <parent>/.worktrees/<repo>-<slug>) maps to its main checkout, so
    the WorktreeCreate hook provisions beside the real repo, not inside a
    sibling worktree."""
    check_dir = _nearest_existing_dir(resolved)
    if not check_dir:
        return None
    toplevel = _git_output(check_dir, "rev-parse", "--show-toplevel")
    if not toplevel:
        return None
    common_dir = _git_output(check_dir, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common_dir and os.path.basename(common_dir) == ".git":
        return os.path.dirname(common_dir)
    return toplevel


def _is_exempt_target(raw_path: str, cwd: str, scratchpad_dir: str) -> bool:
    resolved = _normalize_path(raw_path, cwd)
    exempt_roots = [_normalize_path(root, cwd) for root in EXEMPT_ROOTS]
    if scratchpad_dir:
        exempt_roots.append(_normalize_path(scratchpad_dir, cwd))
    under_exempt_root = any(
        resolved == root or resolved.startswith(root + os.sep) for root in exempt_roots
    )
    return under_exempt_root or not _is_repo_path(_resolve_path(raw_path, cwd))


def _target_repo(order: dict, cwd: str, scratchpad_dir: str) -> tuple[str, list[dict]]:
    """The one git repo an isolation:worktree spawn's non-exempt
    primary_targets live in ("" when every target is exempt). The gate hands
    it to worktree-provision.sh so the worktree follows the order's target,
    not the session's cwd. Targets spanning repos cannot share one worktree."""
    primary_targets = order.get("work_order", {}).get("scope", {}).get("primary_targets", [])
    repos: dict[str, str] = {}
    for target in primary_targets:
        if _is_exempt_target(target, cwd, scratchpad_dir):
            continue
        repo = _main_repo_root(_resolve_path(target, cwd))
        if repo:
            repos.setdefault(repo, target)
    if len(repos) > 1:
        listing = ", ".join(f"{target} -> {repo}" for repo, target in repos.items())
        return "", [
            _err(
                "/work_order/scope/primary_targets",
                "policy.targets_span_repos",
                'isolation: "worktree" gives the worker one worktree in one repo, but '
                f"primary_targets span {len(repos)} repos ({listing}). Split this into "
                "one order per repo.",
            )
        ]
    return next(iter(repos), ""), []


def _check_path_policy(order: dict, cwd: str, scratchpad_dir: str, isolation: str) -> list[dict]:
    primary_targets = order.get("work_order", {}).get("scope", {}).get("primary_targets", [])
    if not primary_targets:
        return []
    all_exempt = all(_is_exempt_target(t, cwd, scratchpad_dir) for t in primary_targets)
    if all_exempt:
        return []
    if isolation == "worktree":
        return []
    if _workspace_managed_by_atask(order):
        # atask claim hands the worker its own worktree; the harness worktree
        # would be a second, redundant one whose isolation guard refuses
        # `atask verify complete` (it reads `complete` as a string-running
        # builtin), which is the worker's only completion path.
        return []
    return [
        _err(
            "/isolation",
            "policy.isolation_required",
            "primary_targets include at least one path inside a git repo outside "
            '~/.agents and ~/.claude; the spawn must set isolation: "worktree", or the '
            "order must declare scope.workspace: atask when the worker claims its "
            "worktree through atask",
        )
    ]


def _workspace_managed_by_atask(order: dict) -> bool:
    return order.get("work_order", {}).get("scope", {}).get("workspace") == "atask"


def _parse_prose_turn_cap(prompt: str) -> int | None:
    match = TURN_CAP_PROSE_RE.search(prompt)
    return int(match.group(1)) if match else None


def _parse_prose_token_budget(prompt: str) -> int | None:
    match = TOKEN_BUDGET_PROSE_RE.search(prompt)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2):  # trailing "k"
        value *= 1000
    return int(value)


def _compile_execution(call_params: dict, prompt: str, defaults: dict) -> dict:
    turn_cap = call_params.get("turn_cap") or _parse_prose_turn_cap(prompt) or defaults["turn_cap"]
    token_budget = (
        call_params.get("token_budget")
        or _parse_prose_token_budget(prompt)
        or defaults["token_budget"]
    )
    return {
        "model": call_params.get("model") or defaults["model"],
        "effort": call_params.get("effort") or defaults["effort"],
        "isolation": call_params.get("isolation") or defaults["isolation"],
        "turn_cap": int(turn_cap),
        "token_budget": int(token_budget),
    }


def _order_id(order: dict) -> str:
    canonical = json.dumps(order, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _posix_path(raw: str) -> str:
    return os.path.expanduser(str(raw)).replace("\\", "/")


def _write_entry_covers_skill(write_entry: str, suffix: str) -> bool:
    posix = _posix_path(write_entry)
    if posix.rstrip("/").endswith(suffix):
        return True
    skill_dir = suffix.rsplit("/", 1)[0]
    if posix.endswith("/**"):
        root = posix[:-3].rstrip("/")
        return root.endswith("/" + skill_dir) or root == skill_dir
    return posix.rstrip("/").endswith("/" + skill_dir) or posix.rstrip("/") == skill_dir


def _banned_skill_paths_to_drop(order: dict) -> list[str]:
    scope = (order.get("work_order") or {}).get("scope") or {}
    required = list(scope.get("required_inputs") or [])
    writes = list(scope.get("allowed_writes") or []) + list(scope.get("primary_targets") or [])
    drop: list[str] = []
    for path in required:
        for suffix in BANNED_IMPLEMENT_SKILL_READS:
            if not _posix_path(path).endswith(suffix):
                continue
            if any(_write_entry_covers_skill(entry, suffix) for entry in writes):
                continue
            drop.append(path)
    return drop


def _strip_banned_required_input_paths(prompt: str, paths: list[str]) -> str:
    if not paths:
        return prompt
    fence = MAIN_FENCE_RE.search(prompt)
    if fence is None:
        return prompt
    body = fence.group(1)
    for path in paths:
        escaped = re.escape(path)
        body = re.sub(
            rf"^[ \t]*-[ \t]+['\"]?{escaped}['\"]?[ \t]*\n",
            "",
            body,
            count=1,
            flags=re.MULTILINE,
        )
    body = re.sub(
        r"(?m)^([ \t]*)required_inputs:[ \t]*\n(?!\1[ \t]+-)",
        "",
        body,
    )
    start, end = fence.span(1)
    return prompt[:start] + body + prompt[end:]


def _inject_compiled_header(prompt: str, order_id: str, execution: dict) -> str:
    """Prepends the order_id and compiled execution parameters as YAML
    comment lines just inside the opening ```yaml fence, so the worker's
    own transcript (SubagentStop's agent_transcript_path) carries both —
    work-order-verify.sh greps the transcript for "work-order-id:" to find
    which state/work-orders/<id>.json describes this spawn, since PreToolUse
    fires before the subagent (and its agent_id) exist."""
    header = (
        f"# work-order-id: {order_id}\n"
        f"# execution: model={execution['model']} effort={execution['effort']} "
        f"isolation={execution['isolation']} turn_cap={execution['turn_cap']} "
        f"token_budget={execution['token_budget']}\n"
        f"{STANDING_OBJECTIVE_COMMENT}"
        f"{DO_NOT_PATH_READ_SKILLS_COMMENT}"
    )
    return prompt.replace("```yaml\n", "```yaml\n" + header, 1)


def _read_envelope() -> dict:
    """stdin envelope built by work-order-gate.sh via jq:
    {prompt, isolation, model, effort, turn_cap, token_budget, cwd, scratchpad_dir}
    """
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def compile_order() -> dict:
    envelope = _read_envelope()
    prompt = envelope.get("prompt") or ""
    cwd = envelope.get("cwd") or os.getcwd()
    scratchpad_dir = envelope.get("scratchpad_dir") or ""

    schema_errors = lint_schema_no_duplicate_keys(SCHEMA_PATH)
    if schema_errors:
        return {
            "ok": False,
            "errors": [_err("$schema", "schema_corrupt", e) for e in schema_errors],
        }

    fence_text = _extract_fence(MAIN_FENCE_RE, prompt)
    if fence_text is None:
        return {
            "ok": False,
            "errors": [
                _err("/", "missing_fence", "prompt has no leading ```yaml work_order block")
            ],
        }

    order, parse_errors = _parse_yaml_order(fence_text)
    if parse_errors:
        # Unparsed YAML cannot accept a JSON Patch; the gate must ask for a
        # fresh full order instead of an order_ref merge (ZYS-737).
        return {"ok": False, "errors": parse_errors, "repairable": False}

    patch_text = _extract_fence(PATCH_FENCE_RE, prompt)
    if patch_text is not None:
        order, patch_errors = _apply_patch(order, patch_text)
        if patch_errors:
            return {"ok": False, "errors": patch_errors}

    schema_violations = _validate_against_schema(order)
    if schema_violations:
        return {"ok": False, "errors": schema_violations}

    isolation = envelope.get("isolation") or ""
    # The isolation policy applies to any order with a declared write scope,
    # not only Claude-typed edit spawns: Hermes delegate_task sends no
    # subagent_type (so is_edit_type is always False there), yet its orders
    # carry allowed_writes and must not slip past the requirement.
    # Read-only orders (explore/reviewer) declare no allowed_writes and stay
    # exempt, exactly as before.
    declares_write_scope = bool(
        order.get("work_order", {}).get("scope", {}).get("allowed_writes")
    )
    if envelope.get("is_edit_type") or envelope.get("harness_worktree_isolation") or declares_write_scope:
        policy_errors = _check_path_policy(order, cwd, scratchpad_dir, isolation)
        if policy_errors:
            return {"ok": False, "errors": policy_errors}

    target_repo = ""
    if isolation == "worktree":
        target_repo, span_errors = _target_repo(order, cwd, scratchpad_dir)
        if span_errors:
            return {"ok": False, "errors": span_errors}

    with DEFAULTS_PATH.open() as fh:
        defaults = json.load(fh)
    execution = _compile_execution(envelope, prompt, defaults)
    order_id = _order_id(order)
    compiled = _inject_compiled_header(prompt, order_id, execution)
    compiled = _strip_banned_required_input_paths(compiled, _banned_skill_paths_to_drop(order))

    return {
        "ok": True,
        "work_order": order,
        "execution": execution,
        "order_id": order_id,
        "target_repo": target_repo,
        "compiled_prompt": compiled,
        "warnings": [],
    }


def target_repo_of_envelope() -> dict:
    """`target-repo` entry point, used by worktree-provision.sh: the repo an
    envelope's order targets ("" when it has none or does not parse). The
    gate already denied invalid and multi-repo orders, so no errors here."""
    envelope = _read_envelope()
    prompt = envelope.get("prompt") or ""
    fence_text = _extract_fence(MAIN_FENCE_RE, prompt)
    if fence_text is None:
        return {"target_repo": ""}
    order, parse_errors = _parse_yaml_order(fence_text)
    if parse_errors:
        return {"target_repo": ""}
    patch_text = _extract_fence(PATCH_FENCE_RE, prompt)
    if patch_text is not None:
        patched, patch_errors = _apply_patch(order, patch_text)
        order = order if patch_errors else patched
    cwd = envelope.get("cwd") or os.getcwd()
    repo, _errors = _target_repo(order, cwd, envelope.get("scratchpad_dir") or "")
    return {"target_repo": repo}


def main(argv: list[str]) -> int:
    if argv[:1] == ["target-repo"]:
        print(json.dumps(target_repo_of_envelope()))
        return 0
    if argv[:1] == ["lint-schema"]:
        target = Path(argv[1]) if len(argv) > 1 else SCHEMA_PATH
        errors = lint_schema_no_duplicate_keys(target)
        result = {"ok": not errors, "errors": [_err("$schema", "duplicate_key", e) for e in errors]}
        print(json.dumps(result))
        return 0
    # default: compile
    print(json.dumps(compile_order()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
