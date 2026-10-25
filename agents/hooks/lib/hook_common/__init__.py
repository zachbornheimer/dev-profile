"""Shared runtime for the Python hooks in ~/.agents/hooks.

Python port of hook-common.sh. A hook is one function
``decide(event: HookEvent) -> Decision | None`` handed to ``run_hook``;
everything around it (stdin, logging, output, fail-open) lives here so no
hook can get it wrong:

    run_hook("my-hook", decide)

Fail-open is the contract: a hook that crashes, times out reading stdin,
or is signalled exits 0 with no decision and leaves a ``fail-open:`` line
in hooks.log. A false block costs far more than a missed check.

Compatibility with hook-common.sh (both run side by side during the port):
  - hooks.log location and ``<iso>\\t<hook>\\t<decision>\\t<detail>`` lines
  - the same HC_* environment overrides (state dir, timeouts, log size,
    reap age/throttle, pinned clock, pinned file mtime, pinned sha256)
  - byte-identical decision JSON to ``jq -n`` (2-space indent, raw UTF-8)
  - Claude Code snake_case and Grok camelCase payload fields

Modules, top-down: runner (entry points) -> decision / event (the
protocol) -> hook_log / settings / clock (state and time) -> shell_command,
signature, git (shared domain nouns).
"""

from .clock import Clock, file_mtime, file_mtime_override_name
from .decision import Decision, DecisionKind
from .event import HookEvent
from .git import GIT, Git, GitResult
from .hook_log import HookLog
from .runner import emit, read_stdin, run_fail_open, run_hook
from .settings import HookSettings
from .shell_command import ShellCommand, is_control_operator
from .signature import command_signature, sha256_digest

__all__ = [
    "GIT",
    "Clock",
    "Decision",
    "DecisionKind",
    "Git",
    "GitResult",
    "HookEvent",
    "HookLog",
    "HookSettings",
    "ShellCommand",
    "command_signature",
    "emit",
    "file_mtime",
    "file_mtime_override_name",
    "is_control_operator",
    "read_stdin",
    "run_fail_open",
    "run_hook",
    "sha256_digest",
]
