# Operations and Troubleshooting

## Normal loop

```text
1. Planner emits one fresh runner.
2. Controller saves it to ~/Downloads.
3. Controller verifies UUID has not already run.
4. Controller executes it synchronously.
5. Runner writes ~/Downloads/<uuid>.zip.
6. Controller attaches the ZIP and sends it.
7. Controller waits ~60 seconds.
8. Controller scans about every 15 seconds for the next runner.
```

## Extract a returned ZIP manually

```bash
mkdir -p /tmp/chatgpt-control-claude-evidence
unzip ~/Downloads/<uuid>.zip -d /tmp/chatgpt-control-claude-evidence
cat /tmp/chatgpt-control-claude-evidence/report.json
```

## Fresh UUID, same runner

Never reuse the old filename.

Conceptually:

```text
run-OLD.py
  ↓ replace OLD everywhere
run-NEW.py
```

Validate the destination does not already exist.

## Symptom: controller returns a ZIP but the runner never ran

Check `report.json` and `term.out.txt`.

If the report says the expected runner ZIP was missing, this is a transport/controller failure. Do not treat it as repository evidence.

Typical causes:

- Download button not activated;
- Save panel did not complete;
- wrong file downloaded;
- execution never started;
- runner crashed before creating its own ZIP.

## Symptom: same run appears to execute twice

This is a UUID deduplication failure.

Risks:

- evidence overwrite;
- duplicate mutations;
- duplicate model calls;
- race-induced false baseline failures.

Fix controller deduplication before interpreting the result.

## Symptom: coding harness appears hung forever

Every model/harness call must have a hard deadline.

If the CLI can emit a complete fenced diff before its process exits, a runner may safely capture the complete diff, give a short grace period, then terminate only that known child process.

Do not globally kill processes named `claude`, `codex`, etc.

## Symptom: stale harness process blocks the next run

Only reap a stale process when evidence is narrow enough to prove it belongs to a prior generated runner, for example:

- cwd is the intended repo;
- command matches the exact previous batch transport;
- process is older than the configured threshold;
- parent is launchd/orphaned or a generated `run-<uuid>.py` process.

Never kill unrelated interactive sessions.

## Symptom: repo-specific gate is red on unrelated files

Use attribution, not wishful thinking.

Compare:

1. current finding;
2. baseline/HEAD finding;
3. files touched by the runner;
4. aggregate-tool messages that may mention multiple files.

A formatter/gate can sometimes attach a global parse failure to an otherwise innocent touched file. Preserve that distinction in evidence.

## Controller implementation notes

The known reliable macOS UI strategy is semantic keyboard/accessibility traversal, not deep recursive AX-tree crawling.

Recommended behavior:

- reset focus;
- reverse-tab through controls;
- stop as soon as the `Download file` button is found;
- activate exactly once;
- save to `~/Downloads`;
- do not resume crawling until synchronous runner execution and evidence return complete.

## When to stop the loop

Stop when:

- acceptance is proved;
- a human decision/credential/action is required;
- the next action would violate safety constraints;
- a dependency is genuinely unavailable;
- the human asks to stop.
