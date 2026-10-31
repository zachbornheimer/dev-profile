"""scope_guard_rules.is_read_only_probe: the deterministic reader skip.

A read-only probe can never mutate state, so judging it wastes a model call and
invites false denials of legitimate help/version/presence checks
(`wt switch --help` was denied in omp_01a18dd0). The skip must never swallow a
command that can act, so redirection and `tee` disqualify the probe.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from scope_guard_rules import is_read_only_probe

PROBES = (
    "wt switch --help",
    "omp --help 2>&1 | head -50",
    "command -v omp",
    "git --version",
    "wt --version",
    "which jq",
    "type -t wt",
)

ACTS = (
    "git commit -S -m fix(ci): replace vulnerable action pins",
    "rm -rf ~/Library/Caches/x",
    "pkill -f node; ps aux --sort=-%cpu | head -20",
    "mise run ci",
    "sed -i '' s/a/b/ f",
    # A help flag on a command that still acts: never a skip.
    "echo --help > /tmp/f",
    "omp --help > /tmp/scope-guard-help.txt",
    "tee /tmp/scope-guard-out",
    "sort -o /tmp/scope-guard-out.txt in.txt",
    # A flag whose spelling merely contains the probe shape.
    "grep --help-pattern x",
    "sed --expression s/a/b/ f",
)


def test_every_probe_is_a_skip() -> None:
    for command in PROBES:
        assert is_read_only_probe(command), ("probe not skipped", command)


def test_no_command_that_can_act_is_skipped() -> None:
    for command in ACTS:
        assert not is_read_only_probe(command), ("acting command skipped", command)


def test_empty_and_plain_work_is_not_a_probe() -> None:
    assert not is_read_only_probe("")
    assert not is_read_only_probe("git push origin HEAD")
