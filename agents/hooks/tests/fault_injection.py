"""Forces a failure inside a hook process. Loaded as ``sitecustomize``.

test_fail_open.py copies this file to ``<tmp>/sitecustomize.py`` and puts
``<tmp>`` on PYTHONPATH, so it runs before the hook's own code in the
``uv run --script`` interpreter. ``HOOK_TEST_FAULT`` picks the fault:

  decide  every HookEvent field read raises — the failure lands inside a
          run_hook hook's ``decide``
  io      JSON parsing, subprocesses, exec, and PATH lookups raise — the
          boundaries every hook, lib-based or not, goes through

Each raise appends one line to ``HOOK_TEST_FAULT_MARKER`` so the test can
prove the fault actually fired rather than passing on an early exit.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys

FAULT_ENV = "HOOK_TEST_FAULT"
MARKER_ENV = "HOOK_TEST_FAULT_MARKER"
DECIDE_FAULT = "decide"
IO_FAULT = "io"
EVENT_MODULE = "hook_common.event"
EVENT_ACCESSORS = ("field", "tool_input", "tool_input_section")


class InjectedFault(RuntimeError):
    """Deliberately not ValueError/OSError, which hooks catch on purpose."""


def _raise_injected(*_args: object, **_kwargs: object) -> None:
    marker = os.environ.get(MARKER_ENV)
    if marker:
        with open(marker, "a", encoding="utf-8") as handle:
            handle.write("fired\n")
    raise InjectedFault("injected by tests/fault_injection.py")


def _break_io() -> None:
    json.loads = _raise_injected
    json.load = _raise_injected
    subprocess.run = _raise_injected
    subprocess.Popen = _raise_injected  # type: ignore[misc]
    shutil.which = _raise_injected
    os.execvp = _raise_injected
    os.execve = _raise_injected


class _BreakEventOnImport(importlib.abc.MetaPathFinder):
    """Patches HookEvent's accessors the moment hook_common.event loads."""

    def find_spec(self, fullname, path, target=None):  # type: ignore[no-untyped-def]
        if fullname != EVENT_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        original_exec = spec.loader.exec_module

        def exec_and_break(module):  # type: ignore[no-untyped-def]
            original_exec(module)
            for name in EVENT_ACCESSORS:
                setattr(module.HookEvent, name, _raise_injected)

        spec.loader.exec_module = exec_and_break  # type: ignore[method-assign]
        return spec


match os.environ.get(FAULT_ENV):
    case "io":
        _break_io()
    case "decide":
        sys.meta_path.insert(0, _BreakEventOnImport())
