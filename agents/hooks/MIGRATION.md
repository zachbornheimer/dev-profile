# Porting a shell hook to Python

Exemplar: `gate-bypass-tripwire.py` + `tests/test_gate_bypass_tripwire.py`. Copy their shape.

## 1. File and header

`<same-stem>.py` next to the `.sh` (registrations swap by extension only). `chmod +x`. Top of file:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""<Event> (<matcher>) — what it denies/injects, and why (keep the .sh header's reasoning)."""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from hook_common import Decision, HookEvent, ShellCommand, run_hook
```

Stdlib only. `>=3.10` because the lib uses `match` and `slots=True` (so a hook with a bare `python3` shebang, which can be 3.9, must not import it).

## 2. Lib API (`lib/hook_common/`, imported as `hook_common`)

One package, one module per concept: `runner`, `decision`, `event`, `hook_log`, `settings`, `clock`, `shell_command`, `signature`, `git`. Import from `hook_common`, never from a submodule.

Entry points (both always fail open: an exception, a stdin timeout, or SIGINT/SIGTERM is logged as `fail-open:`):

- `run_hook(name, decide) -> NoReturn`: for a hook that speaks the decision protocol. Reads stdin (5 s budget), logs, prints, exits 0. Never call `sys.exit` or `print` yourself.
- `run_fail_open(name, main, fallback_output="") -> NoReturn`: for an entry point that owns its protocol (a CLI mode, a Cursor response shape). `main()`'s return is the exit status; an exception prints `fallback_output` (e.g. `"{}"`) and exits 0.
- `decide(event: HookEvent) -> Decision | None`: `None` means silent with no log line, the .sh's bare `exit 0`.

The protocol:

- `HookEvent`: `.tool_name` (Grok aliases normalized), `.event_name`, `.session_id`, `.subagent_type` (also Grok's `toolInput.subagentType`), `.field(snake, camel)`, `.tool_input(name)`, `.tool_input_section() -> dict`. Values come back as text, `""` when absent; semantics match jq `//` (a present `""` wins).
- `Decision.deny(reason, *, log_detail=None)`, `.allow(reason, *, updated_input=None, log_label="allow", log_detail=None)`, `.no_objection(detail, log_label="allow")` (logs, prints nothing), `.block(reason)` (Stop), `.context(text, event_name, log_label="allow", *, log_detail=None)`. JSON is byte-identical to the .sh's `jq -n`. `updated_input` adds `updatedInput`. `log_detail` makes hooks.log record a shorter detail than the printed reason, when the .sh's `hc_log` did (a signature, a counter).
- `emit(decision, log)`: what `run_hook` does with a Decision; for `run_fail_open` hooks that print one.
- `read_stdin(timeout_secs) -> str | None`: `None` on timeout.

Shared nouns (each keeps its `hook-common.sh` env override):

- `ShellCommand.parse(cmd) -> ShellCommand | None`: `.words` and `.segments()`, split at `&& || ; | & ( )`. `None` when the quoting is unparseable. Take the stricter path then; never treat it as "no words".
- `command_signature(text) -> str` (`hc_command_signature`: first 3 words, skipping `NAME=value` anywhere), `sha256_digest(text, env=os.environ) -> str` (`hc_sha256`, honors `HC_SHA256_OVERRIDE`).
- `file_mtime(path, env=os.environ) -> int | None` (`hc_file_mtime`, honors `HC_FILE_MTIME_OVERRIDE_<sanitized path>`), `file_mtime_override_name(path) -> str`.
- `Git().run(directory, *args, timeout=None) -> GitResult` (`GIT` is the default instance). `GitResult(exit_code, stdout)` unpacks as a tuple; `.ok`, `.text` (stripped stdout on success, else `""`). A missing git or a timeout is a failed run, never an exception. Hook-specific git facades put domain verbs on top of it.
- `HookLog(name, settings, clock).record(decision, detail)` / `.record_fail_open(cause)`, `HookSettings.from_env()`, `Clock.from_env()`: already wired by the entry points. They honor every `HC_*` override.

If you need more of `hook-common.sh` (heredoc stripping, ...), port it into the lib as a noun with its env override, not into your hook.

## 3. Hook body

Build it from pure functions over values: word-layer rules take a `Segment`, and each check returns a reason or `None`. Put I/O (reading a file, calling git) in one small named function. Name every string and number as a constant: reasons, flags, file names.

## 4. Tests: `tests/test_<stem_with_underscores>.py`

1. `FIXTURE_CASES`: one `FixtureCase(fixture, DENY|SILENT)` per `expect_*` line for this hook in `tests/run.sh`, in the same order. Grep run.sh for the hook's other assertions (`expect_context`, `expect_stop_block`, reason-contains) and cover those too.
2. `test_port_decides_like_run_sh`: runs the `.py` through the `hooks` fixture (`HookRunner`) and asserts `assert_clean_run` plus the decision.
3. Parity (`@pytest.mark.parity`): runs the same inputs through `.py` and `.sh`. It requires equal `output` and equal `log`. Also add `PAYLOAD_CASES` for paths the fixtures miss: Grok camelCase, empty stdin, disk reads, and unparseable input.
4. State across calls (`tests/hook_harness.py`): `hooks.session(name, env)` is a `HookSession` whose state dir persists across calls (`.run_payload`, `.run_fixture`, `.seed(name, lines)`, `.write(name, text)`, `.log`); each `HookRun.log` holds only what that call appended. `hooks.twins(stem, env)` runs every step through `<stem>.sh` and `<stem>.py` in two sessions and returns `(sh_run, py_run)`. A stateful hook also gets a cross-language test: the `.sh` writes the state, the `.py` reads it, and the result must equal the `.sh` reading it (the swap happens mid-session).
5. Fail-open is covered for every entry file automatically by `tests/test_fail_open.py` (malformed JSON, a wrong-shaped payload, a fault inside `decide`, a fault at every I/O boundary). A hook with a deliberate non-zero status adds a `Contract` there, with its reason.
6. Run `cd ~/.agents/hooks && uv run --with pytest pytest tests/test_<stem>.py -q`.
7. Prove red: inject a `raise` into `decide` and watch the allow cases fail on `failed_open`, then restore.

## 5. Gotchas that cost the first port turns

- The live tripwire denies any Write/Edit, docs included, that adds a line with one of its `SUPPRESSION_PRAGMAS`. Don't name them in prose. Test data that contains one should be read from an existing fixture.
- The live tripwire's Bash text layer denies any command containing both `git` and `--no-verify`, even inside a heredoc body. Write files with the Write tool, not `cat <<EOF`.
- quality-guard flags `x == "..."` when `x` is named `token` (secret heuristic). Name shell words `word`.
- Keep the `.sh`, `tests/run.sh`, fixtures, and registrations untouched. The swap happens centrally.

## Checklist

- [ ] `.py` is executable, has the header, stdlib only, and uses `run_hook` (or `run_fail_open` for its own protocol)
- [ ] every run.sh case for the hook is in `FIXTURE_CASES`, and they all pass
- [ ] parity passes on fixtures and payload cases (output and log)
- [ ] red proven by an injected failure
- [ ] the report lists every .sh quirk found: whether you replicated it or diverged, and why
