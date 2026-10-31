#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash and Edit|Write matchers) — gate-bypass tripwire.

Denies the mechanical patterns that let an agent route around a quality
gate instead of fixing what the gate caught: --no-verify (or git commit -n),
git -c core.hooksPath=..., a forced push to a protected branch, in-place
sed/perl edits to lockfiles, a newly-added suppression pragma, or a
hand-edit to a generated file (/.generated/ tree, *.generated.*, *.gen.*).
Per code-standards.md ("a false positive is a code smell"), the fix for a
real hit is never to suppress the gate — make the code unmistakable, or fix
the rule or generator at its source.

Bash commands are checked in two layers, in union:
  1. Word layer — whole shell words per simple command (ShellCommand), so
     a quoted flag is still live and a quoted sentence mentioning one is not.
  2. Text layer — regex over the command with quoted spans blanked, the only
     layer that sees a flag built by command substitution (`...` or $(...)).
     It also runs alone when the quoting can't be parsed at all.

Fails OPEN (via run_hook) on any parse error or unexpected input.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from eval_code import shell_candidates
from hook_common import Decision, HookEvent, ShellCommand, run_hook

HOOK_NAME = "gate-bypass-tripwire"

# Only a net-new occurrence trips: removing one, or an edit whose old text
# already had it, is untouched. Counted per LINE, as the shell hook did.
SUPPRESSION_PRAGMAS = (
    "nolint",
    "noqa",
    "@ts-ignore",
    "@ts-expect-error",
    "eslint-disable",
    "phpcs:ignore",
    "rubocop:disable",
)
GENERATED_TREE_MARKER = "/.generated/"
GENERATED_NAME_GLOBS = ("?*.generated.*", "?*.gen.*")
# A bare push or HEAD could be main/master, so both count as protected.
PROTECTED_PUSH_TARGETS = frozenset({"", "HEAD", "main", "master"})
FORCE_FLAGS = frozenset({"--force", "-f"})
IN_PLACE_EDITORS = frozenset({"sed", "perl"})
IN_PLACE_FLAG = re.compile(r"-[a-zA-Z]*i[a-zA-Z]*")
LOCKFILE_NAMES = frozenset({"package-lock.json", "pnpm-lock.yaml"})
HOOKS_PATH_SETTING = "core.hooksPath="
# ZYS-1758: switches that turn the hook runner off without a git flag.
# hk (HK=0, HK_SKIP_HOOK[S]), husky (HUSKY=0), lefthook (LEFTHOOK=0).
HOOK_OFF_ENV = re.compile(r"(HK|HUSKY|LEFTHOOK)=(0|false|no|off)", re.IGNORECASE)
HOOK_SKIP_ENV = re.compile(
    r"(HK_SKIP_HOOKS?|LEFTHOOK_EXCLUDE)=.+|MISE_HISTORY_ALLOW_PLAINTEXT_HISTORY=(1|true|yes|on)",
    re.IGNORECASE,
)
MISE_PLAINTEXT_SETTING_RE = re.compile(
    r"\b(history\.)?allow_plaintext_history\s*=\s*(true|1)\b", re.IGNORECASE
)
# Git config injected through the environment (git >= 2.31 / GIT_CONFIG_PARAMETERS).
GIT_CONFIG_ENV = re.compile(
    r"(GIT_CONFIG_PARAMETERS|GIT_CONFIG_KEY_\d+)=.*", re.IGNORECASE
)
# Config keys whose value disables hooks; matched case-insensitively like git does.
HOOK_DISABLING_KEYS = re.compile(
    r"(core\.hookspath|hk\.skiphooks?|hook\.[^.=\s]+\.enabled)", re.IGNORECASE
)
NESTING_SHELLS = frozenset({"sh", "bash", "zsh", "dash"})
# Helpers that push to main with --no-verify baked in (dotfiles push-origin-main.zsh).
HOOK_SKIPPING_HELPERS = frozenset({"push-origin-main"})
SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".pl", ".rb")

NO_VERIFY_REASON = (
    "This command runs git commit with --no-verify (or its short form -n), bypassing a "
    "pre-commit/pre-push hook. Fix what the hook would catch instead of skipping it; only "
    "bypass with the user's explicit, direct instruction."
)
FORCE_PUSH_REASON = (
    "This command force-pushes to '{target}', a destructive rewrite of a protected/ambiguous "
    "target's history — a bare push or HEAD is treated as protected because it could be "
    "main/master. This requires the user's explicit, direct instruction — never issue it on "
    "inference. Name a specific non-protected branch if that's genuinely the intent."
)
UNNAMED_PUSH_TARGET = "<no ref named>"
LOCKFILE_REASON = (
    "This command hand-edits a lockfile (package-lock.json/pnpm-lock.yaml) in place with "
    "sed/perl. Lockfiles are generated artifacts — regenerate via the package manager (npm "
    "install / pnpm install) instead of patching the file directly."
)
HOOKS_PATH_REASON = (
    "This command sets git's core.hooksPath via -c, disabling every git hook for this "
    "invocation. Fix what the hook would catch instead of routing around it — bypassing hooks "
    "via hooksPath is still bypassing. Only do this with the user's explicit, direct instruction."
)
HOOK_ENV_REASON = (
    "This command turns git hooks off through the environment (HK=0, HK_SKIP_HOOK, HUSKY=0, "
    "LEFTHOOK=0, or GIT_CONFIG_* carrying a hook setting). That is the same bypass as "
    "--no-verify. Fix what the hook would catch instead; only bypass with the user's "
    "explicit, direct instruction."
)
HOOK_CONFIG_REASON = (
    "This command changes git config to disable or skip hooks (core.hooksPath, hk.skipHook, "
    "hook.<name>.enabled). Every later commit and push in this clone would then skip the gate. "
    "Fix what the hook would catch instead; only do this with the user's explicit, direct "
    "instruction."
)
HELPER_REASON = (
    "This helper pushes to main with --no-verify built in, so the pre-push gate never runs. "
    "Push with plain `git push` (hooks on) or open a pull request instead."
)
WT_REASON = (
    "This worktrunk command passes --no-hooks/--no-verify, which skips the project's "
    "pre-merge and pre-commit hooks before main moves. Run it without the flag and fix what "
    "the hook catches; only skip with the user's explicit, direct instruction."
)
MISE_PLAINTEXT_REASON = (
    "This command or config enables allow-plaintext-history, bypassing mise's pre-push "
    "secret and encryption history check. Purge the plaintext version with `mise dot history "
    "purge <path>` and encrypt the file (`encrypt = true`) instead; only bypass with the "
    "user's explicit, direct instruction."
)
SCRIPT_REASON = (
    "This file is a script that runs git with hooks skipped (--no-verify, HK=0, HUSKY=0, "
    "core.hooksPath). Writing the bypass into a script and running it is still bypassing the "
    "gate. Remove the bypass; only add one with the user's explicit, direct instruction."
)
TEXT_NO_VERIFY_REASON = (
    "This command runs git with --no-verify, bypassing a pre-commit/pre-push hook. Fix what "
    "the hook would catch instead of skipping it; only bypass with the user's explicit, direct "
    "instruction."
)
TEXT_SHORT_N_REASON = (
    "This command runs git commit with -n (short form of --no-verify), bypassing a pre-commit "
    "hook. Fix what the hook would catch instead of skipping it; only bypass with the user's "
    "explicit, direct instruction."
)
TEXT_FORCE_PUSH_REASON = (
    "This command force-pushes to main/master, a destructive rewrite of a protected branch's "
    "history. This requires the user's explicit, direct instruction — never issue it on "
    "inference."
)
GENERATED_TREE_REASON = (
    "This path is inside a /.generated/ tree — a hand-edit here gets silently overwritten by "
    "the next regeneration and diverges the generated artifact from its source. Fix the "
    "generator or the upstream source instead."
)
GENERATED_NAME_REASON = (
    "This file is generated (*.generated.* / *.gen.*) — a hand-edit gets silently overwritten "
    "by the next regeneration. Fix the generator or the upstream source, then regenerate."
)
PRAGMA_REASON = (
    "This edit adds a new '{pragma}' suppression pragma. A suppression pragma pattern-matches "
    "a gate bypass. Rewrite the code to be unmistakable, or fix the generator/rule at its source."
)

Segment = tuple[str, ...]


# --- word layer: one simple command (segment) at a time ----------------------


def commits_without_verify(segment: Segment) -> bool:
    in_git = has_commit = has_no_verify = has_short_n = False
    for word in segment:
        in_git = in_git or word == "git"
        has_commit = has_commit or (in_git and word == "commit")
        has_no_verify = has_no_verify or word == "--no-verify"
        has_short_n = has_short_n or word == "-n"
    return in_git and (has_no_verify or (has_commit and has_short_n))


def protected_force_push_target(segment: Segment) -> str | None:
    """The protected ref a forced push names ("" for none), or None if safe."""
    in_git = in_push = has_force = False
    target = ""
    for word in segment:
        in_git = in_git or word == "git"
        in_push = in_push or (in_git and word == "push")
        has_force = has_force or word in FORCE_FLAGS
        if in_push and word != "push" and not word.startswith("-"):
            target = word
    if in_push and has_force and target in PROTECTED_PUSH_TARGETS:
        return target
    return None


def edits_lockfile_in_place(segment: Segment) -> bool:
    return (
        any(word in IN_PLACE_EDITORS for word in segment)
        and any(IN_PLACE_FLAG.fullmatch(word) for word in segment)
        and any(word.rsplit("/", 1)[-1] in LOCKFILE_NAMES for word in segment)
    )


def disables_git_hooks(segment: Segment) -> bool:
    in_git = previous_was_c = False
    for word in segment:
        in_git = in_git or word == "git"
        if not in_git:
            continue
        if previous_was_c and word.startswith(HOOKS_PATH_SETTING):
            return True
        if word.startswith("-c" + HOOKS_PATH_SETTING):
            return True
        previous_was_c = word == "-c"
    return False


def sets_hook_env(segment: Segment) -> bool:
    """Leading VAR=val words, `env VAR=val`, or `export VAR=val` that switch hooks off."""
    for word in segment:
        if HOOK_OFF_ENV.fullmatch(word) or HOOK_SKIP_ENV.fullmatch(word):
            return True
        if GIT_CONFIG_ENV.fullmatch(word) and HOOK_DISABLING_KEYS.search(word):
            return True
    return False


def config_disables_hooks(segment: Segment) -> bool:
    """`git config [scope] <hook key> <value>` (a write) or `git -c <hook key>=...`."""
    in_git = previous_was_c = False
    in_config = False
    for word in segment:
        in_git = in_git or word == "git"
        if not in_git:
            continue
        if previous_was_c and HOOK_DISABLING_KEYS.match(word) and "=" in word:
            return True
        if (
            word.startswith("-c")
            and len(word) > 2
            and HOOK_DISABLING_KEYS.match(word[2:])
        ):
            return True
        previous_was_c = word == "-c"
        if word == "config":
            in_config = True
            continue
        if in_config and HOOK_DISABLING_KEYS.fullmatch(word):
            # a read (--get, --list, ...) has a flag before the key; a write does not
            return not any(
                w
                in (
                    "--get",
                    "--get-all",
                    "--get-regexp",
                    "--list",
                    "-l",
                    "--unset",
                    "--unset-all",
                )
                for w in segment
            )
    return False


WT_HOOK_SKIP_FLAGS = frozenset({"--no-hooks", "--no-verify"})


def worktrunk_skips_hooks(segment: Segment) -> bool:
    """`wt merge|step commit|... --no-hooks` skips wt's pre-merge/pre-commit gate."""
    return (
        bool(segment)
        and segment[0] == "wt"
        and any(w in WT_HOOK_SKIP_FLAGS for w in segment)
    )


def bypasses_mise_history_gate(segment: Segment) -> bool:
    if "--allow-plaintext-history" in segment:
        return True
    joined = " ".join(segment).lower()
    return (
        "mise" in segment
        and "settings" in segment
        and "history.allow_plaintext_history" in joined
        and any(
            tok
            in (
                "true",
                "1",
                "history.allow_plaintext_history=true",
                "history.allow_plaintext_history=1",
            )
            for tok in joined.split()
        )
    )


def runs_hook_skipping_helper(segment: Segment) -> bool:
    return bool(segment) and segment[0] in HOOK_SKIPPING_HELPERS


def nested_shell_scripts(segment: Segment) -> list[str]:
    """The script strings of `sh -c '...'` (and bash/zsh/dash), to re-check."""
    found = []
    for i, word in enumerate(segment[:-1]):
        if word.rsplit("/", 1)[-1] in NESTING_SHELLS and "-c" in segment[i + 1 : i + 3]:
            j = segment.index("-c", i + 1)
            if j + 1 < len(segment):
                found.append(segment[j + 1])
    return found


def _any_segment(segments: Iterable[Segment], rule: Callable[[Segment], bool]) -> bool:
    return any(rule(segment) for segment in segments)


def word_layer_reason(command: ShellCommand) -> str | None:
    segments = command.segments()
    if _any_segment(segments, commits_without_verify):
        return NO_VERIFY_REASON
    for segment in segments:
        target = protected_force_push_target(segment)
        if target is not None:
            return FORCE_PUSH_REASON.format(target=target or UNNAMED_PUSH_TARGET)
    if _any_segment(segments, edits_lockfile_in_place):
        return LOCKFILE_REASON
    if _any_segment(segments, disables_git_hooks):
        return HOOKS_PATH_REASON
    if _any_segment(segments, sets_hook_env):
        return HOOK_ENV_REASON
    if _any_segment(segments, config_disables_hooks):
        return HOOK_CONFIG_REASON
    if _any_segment(segments, runs_hook_skipping_helper):
        return HELPER_REASON
    if _any_segment(segments, worktrunk_skips_hooks):
        return WT_REASON
    if _any_segment(segments, bypasses_mise_history_gate):
        return MISE_PLAINTEXT_REASON
    return None


# --- text layer: line-oriented regex, quoted spans blanked -------------------

SINGLE_QUOTED_SPAN = re.compile(r"'[^'\n]*'")
DOUBLE_QUOTED_SPAN = re.compile(r'"[^"\n]*"')


@dataclass(frozen=True, slots=True)
class UnquotedText:
    """A command with every quoted span's contents blanked, searched line by line."""

    lines: tuple[str, ...]

    @classmethod
    def of(cls, command: str) -> UnquotedText:
        blanked = SINGLE_QUOTED_SPAN.sub("''", command)
        blanked = DOUBLE_QUOTED_SPAN.sub('""', blanked)
        return cls(tuple(blanked.split("\n")))

    def has(self, pattern: str) -> bool:
        compiled = re.compile(pattern)
        return any(compiled.search(line) for line in self.lines)


def text_layer_reason(command: str) -> str | None:
    text = UnquotedText.of(command)
    if text.has(r"\bgit\b") and text.has(r"--no-verify\b"):
        return TEXT_NO_VERIFY_REASON
    if text.has(r"\bgit\b\s+commit\b") and text.has(r"(^| )-n( |$)"):
        return TEXT_SHORT_N_REASON
    if (
        text.has(r"\bgit\b.*\bpush\b")
        and text.has(r"(--force\b|(^| )-f( |$))")
        and text.has(r"\b(main|master)\b")
    ):
        return TEXT_FORCE_PUSH_REASON
    if text.has(r"\b(sed|perl)\b.*\s-[a-zA-Z]*i[a-zA-Z]*\b") and text.has(
        r"(package-lock\.json|pnpm-lock\.yaml)"
    ):
        return LOCKFILE_REASON
    return None


MAX_NESTING = 3


def bash_bypass_reason(command: str, depth: int = 0) -> str | None:
    parsed = ShellCommand.parse(command)
    word_reason = word_layer_reason(parsed) if parsed is not None else None
    if word_reason is None and parsed is not None and depth < MAX_NESTING:
        for segment in parsed.segments():
            for inner in nested_shell_scripts(segment):
                word_reason = bash_bypass_reason(inner, depth + 1)
                if word_reason:
                    break
            if word_reason:
                break
    return word_reason or text_layer_reason(command)


# --- scripts written to disk (zq#102: "Pushed via /tmp script with --no-verify") ---

SCRIPT_BYPASS_LINE = re.compile(
    r"--no-verify\b|--allow-plaintext-history\b|\b(HK|HUSKY|LEFTHOOK)=[\"']?(0|false)\b|\bMISE_HISTORY_ALLOW_PLAINTEXT_HISTORY=[\"']?(1|true|yes|on)\b|\bHK_SKIP_HOOKS?=|core\.hooksPath",
    re.IGNORECASE,
)


def is_script(file_path: str, content: str) -> bool:
    return file_path.endswith(SCRIPT_SUFFIXES) or content.startswith("#!")


def script_bypass_reason(file_path: str, old_text: str, new_text: str) -> str | None:
    """A net-new line in a script that runs git with hooks skipped."""
    if not is_script(file_path, new_text):
        return None

    def hits(text: str) -> int:
        count = 0
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("#", "//")) and not stripped.startswith("#!"):
                continue
            if (
                "git" in line
                and SCRIPT_BYPASS_LINE.search(line)
                or "--allow-plaintext-history" in line
                or re.search(
                    r"\b(HK|HUSKY|LEFTHOOK)=[\"']?(0|false)\b|\bMISE_HISTORY_ALLOW_PLAINTEXT_HISTORY=[\"']?(1|true|yes|on)\b",
                    line,
                    re.IGNORECASE,
                )
            ):
                count += 1
        return count

    return SCRIPT_REASON if hits(new_text) > hits(old_text) else None


# --- Edit / Write -------------------------------------------------------------


def lines_containing(text: str, needle: str) -> int:
    return sum(1 for line in text.split("\n") if needle in line)


def file_edit_reason(file_path: str, old_text: str, new_text: str) -> str | None:
    if GENERATED_TREE_MARKER in file_path:
        return GENERATED_TREE_REASON
    basename = file_path.rsplit("/", 1)[-1]
    if any(fnmatchcase(basename, glob) for glob in GENERATED_NAME_GLOBS):
        return GENERATED_NAME_REASON
    for pragma in SUPPRESSION_PRAGMAS:
        if lines_containing(new_text, pragma) > lines_containing(old_text, pragma):
            return PRAGMA_REASON.format(pragma=pragma)
    if file_path.endswith(".toml") and len(
        MISE_PLAINTEXT_SETTING_RE.findall(new_text)
    ) > len(MISE_PLAINTEXT_SETTING_RE.findall(old_text)):
        return MISE_PLAINTEXT_REASON
    return script_bypass_reason(file_path, old_text, new_text)


def existing_text(file_path: str) -> str:
    """Current on-disk content a Write would replace; "" if unreadable."""
    try:
        return Path(file_path).read_bytes().decode("utf-8", errors="surrogateescape")
    except OSError:
        return ""


# --- entry ----------------------------------------------------------------------


def _verdict(reason: str | None, tool_name: str) -> Decision:
    if reason is not None:
        return Decision.deny(reason)
    return Decision.no_objection(f"{tool_name}:no-bypass-pattern")


# omp runs run_command as `write xd://<server>_run_command` with the call's JSON
# as `content`, or as `tool.<server>_run_command({...})` inside `eval` code, and
# its bridge passes those raw tool names (ZYS-1758: the --no-verify push and the
# HK=0 commit both took the `write xd://` route).
XD_TOOL = re.compile(r"^xd://(?P<server>[\w.-]+)$")


def xd_run_command(event: HookEvent) -> str | None:
    """The shell command of an omp `write xd://…` that runs run_command, else None.

    Two shapes: `xd://<server>_run_command` with {"command": …}, and the meta
    gateway `xd://<server>_exec` with {"name": "run_command", "input": {"command": …}}.
    """
    target = XD_TOOL.match(event.tool_input("file_path"))
    if target is None:
        return None
    try:
        call = json.loads(event.tool_input("content") or "{}")
    except ValueError:
        call = {}
    if not isinstance(call, dict):
        call = {}
    if target["server"].endswith("run_command"):
        command = call.get("command")
    elif str(call.get("name", "")).endswith("run_command") and isinstance(
        call.get("input"), dict
    ):
        command = call["input"].get("command")
    else:
        return None
    return command if isinstance(command, str) else ""


EVAL_RUN_COMMAND = re.compile(r"\b[\w.]*run_command\b")
JSON_COMMAND_FIELD = re.compile(r'"command"\s*:\s*("(?:[^"\\]|\\.)*")')


def eval_run_commands(code: str) -> list[str]:
    """Every `"command": "…"` string in eval code that calls a run_command tool."""
    if not EVAL_RUN_COMMAND.search(code):
        return []
    found: list[str] = []
    for literal in JSON_COMMAND_FIELD.findall(code):
        try:
            found.append(json.loads(literal))
        except ValueError:
            continue
    return found


def decide(event: HookEvent) -> Decision | None:
    tool_name = event.tool_name
    xd_command = xd_run_command(event) if tool_name == "Write" else None
    if xd_command is not None:
        return _verdict(
            bash_bypass_reason(xd_command) if xd_command else None, "run_command"
        )
    if event.raw_tool_name == "eval":
        code = event.tool_input("code")
        language = event.tool_input("language") or "py"
        # run_command JSON fields, then every literal / argv list / env skip the
        # code can hand a shell (lib/eval_code.py; ZYS-1758 ruling 3).
        commands = eval_run_commands(code) + shell_candidates(code, language)
        reasons = (bash_bypass_reason(c) for c in commands)
        return _verdict(next((r for r in reasons if r), None), "eval")
    match tool_name:
        case "Bash":
            command = event.tool_input("command")
            if not command:
                return None
            return _verdict(bash_bypass_reason(command), tool_name)
        case "Edit" | "Write":
            file_path = event.tool_input("file_path")
            if not file_path:
                return None
            if tool_name == "Edit":
                old_text = event.tool_input("old_string")
                new_text = event.tool_input("new_string")
            else:
                old_text = existing_text(file_path)
                new_text = event.tool_input("content")
            return _verdict(file_edit_reason(file_path, old_text, new_text), tool_name)
        case _:
            return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
