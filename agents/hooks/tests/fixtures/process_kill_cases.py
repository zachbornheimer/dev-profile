"""Command table for test_process_kill_guard.py: what the process-kill rules deny and allow.

Data only. Nothing here runs pkill/killall; each command is only ever parsed.
"""

from __future__ import annotations

from dataclasses import dataclass

DENY = "deny"
SILENT = "none"
WRAPPER = "pkill-aged"


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    command: str
    expected: str


CASES = (
    # wt / worktrunk targets, every disguise.
    Case("wt-step-commit-deny", 'pkill -f "wt step commit"', DENY),
    Case("wt-regex-deny", 'pkill -f "wt.*"', DENY),
    Case("wt-bare-f-deny", "pkill -f wt", DENY),
    Case("wt-name-match-deny", "pkill wt", DENY),
    Case("wt-exact-deny", "pkill -x wt", DENY),
    Case("wt-anchored-regex-deny", "pkill -f '^wt '", DENY),
    Case("wt-space-regex-deny", "pkill -f 'wt .*'", DENY),
    Case("wt-alternation-deny", "pkill -f 'wt|vite'", DENY),
    Case("wt-word-boundary-regex-deny", r"pkill -f '\bwt\b'", DENY),
    Case("wt-full-path-binary-deny", "pkill -f /opt/homebrew/bin/wt", DENY),
    Case("worktrunk-deny", "pkill -f worktrunk", DENY),
    Case("killall-wt-deny", "killall wt", DENY),
    Case("killall-signal-wt-deny", "killall -s TERM wt", DENY),
    Case("sudo-pkill-wt-deny", "sudo pkill -f wt", DENY),
    Case("pkill-full-path-deny", "/usr/bin/pkill -f 'wt step'", DENY),
    Case("env-wrapped-deny", "env FOO=1 pkill -f wt", DENY),
    Case("timeout-wrapped-deny", "timeout 5 pkill -f wt", DENY),
    Case("after-and-deny", "echo hi && pkill -f wt", DENY),
    Case("after-pipe-deny", "echo hi | pkill -f wt", DENY),
    Case("nested-bash-c-deny", "bash -c 'pkill -f \"wt step commit\"'", DENY),
    Case("xargs-kill-pgrep-deny", "pgrep -f wt | xargs kill", DENY),
    Case("xargs-kill-9-pgrep-deny", "pgrep -f 'wt step' | xargs kill -9", DENY),
    Case("sudo-xargs-kill-deny", "pgrep -f wt | sudo xargs kill", DENY),
    Case("kill-subshell-pgrep-deny", "kill $(pgrep -f 'wt step commit')", DENY),
    Case("kill-9-subshell-pgrep-deny", "kill -9 $(pgrep -f wt)", DENY),
    Case(
        "ps-grep-xargs-kill-deny",
        "ps aux | grep wt | awk '{print $2}' | xargs kill",
        DENY,
    ),
    Case("xargs-pkill-deny", "echo wt | xargs pkill -f", DENY),
    # Broad pkill -f without an age limit is steered to the wrapper.
    Case("pkill-f-vite-deny", "pkill -f vite", DENY),
    Case("pkill-f-with-O-flag-deny", "pkill -O 300 -f foo", DENY),
    Case("pkill-signal-f-deny", "pkill -TERM -f 'node server'", DENY),
    Case("pkill-fx-cluster-deny", "pkill -fx vite", DENY),
    # Allowed: the safe wrapper, narrow scopes, inspection, data mentioning kill.
    Case("wrapper-vite-allow", f"{WRAPPER} -f vite", SILENT),
    Case("wrapper-wt-allow", f"{WRAPPER} -f wt", SILENT),
    Case("wrapper-min-age-allow", f"{WRAPPER} -O 600 -f vite", SILENT),
    Case("wrapper-full-path-allow", "~/.agents/bin/pkill-aged -f vite", SILENT),
    Case("pkill-own-children-allow", "pkill -P $$ -f sleep", SILENT),
    Case("pkill-name-only-allow", "pkill vite", SILENT),
    Case("killall-other-allow", "killall Finder", SILENT),
    Case("pgrep-inspect-wt-allow", "pgrep -f wt", SILENT),
    Case("pgrep-inspect-long-wt-allow", "pgrep -lf 'wt step'", SILENT),
    Case("ps-grep-wt-no-kill-allow", "ps aux | grep wt", SILENT),
    Case("kill-pid-allow", "kill 12345", SILENT),
    Case("pgrep-other-xargs-kill-allow", "pgrep -f vite | xargs kill", SILENT),
    # False-positive guards: wt must be a whole word, not part of another name.
    Case("swt-pattern-allow", "pkill swt", SILENT),
    Case("wtf-pattern-allow", "pkill wtf", SILENT),
    Case("path-with-wt-dir-allow", "pkill /Users/zbornheimer/wt/server", SILENT),
    Case("hyphenated-wt-name-allow", "pkill my-wt-proxy", SILENT),
    Case("network-pattern-allow", "pkill network", SILENT),
    Case("grep-wt-xargs-kill-other-allow", "pgrep -f swt | xargs kill", SILENT),
    Case("echo-mentions-allow", 'echo "pkill -f wt"', SILENT),
    Case("commit-message-mentions-allow", 'git commit -m "block pkill -f wt"', SILENT),
    Case("heredoc-body-allow", "cat <<'EOF'\npkill -f wt\nEOF\n", SILENT),
    Case("wt-cli-itself-allow", "wt step commit", SILENT),
    Case("unrelated-allow", "ls -la", SILENT),
)
