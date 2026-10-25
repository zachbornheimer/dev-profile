# Current proven loop

The current known-good automated path is:

```text
ChatGPT emits run-<uuid>.py
→ macOS controller semantically finds the newest Download file
→ native Save panel is forced to ~/Downloads
→ controller runs: PROVIDER=<name> uv run -- ~/Downloads/run-<uuid>.py
  or PROVIDER=<name> uv run python ~/Downloads/run-<uuid>.zip
→ runner/controller ensure ~/Downloads/<uuid>.zip exists
→ controller focuses ChatGPT and pastes the ZIP
→ Enter
→ bounded retry Enter
→ 60 second cooldown
→ scan about every 15 seconds for the next fresh UUID
```

## Current controller facts

The included `controller/agentmux-autoloop-v9.py` is the exact current controller
used by the working loop at the time this starter was packaged.

Important behavior:

- semantic reverse-focus traversal (`Shift-Tab`);
- no full recursive Accessibility-tree crawl;
- once `Download file` is found, traversal stops immediately;
- Save panel readiness is detected from the focused `AXTextField`;
- destination is forced to `~/Downloads`;
- UUIDs are deduplicated and never intentionally re-executed;
- runner execution is synchronous, so the controller does not crawl while work runs;
- after evidence return, the controller waits 60 seconds before any new crawl;
- later scans use a bounded ~15 second cadence;
- 10 minute deadman behavior is bounded;
- controller fallback ZIPs are transport evidence, not proof the runner executed;
- the second Enter used as a send retry can create duplicate send/attachment behavior
  in some UI states and is a known future hardening item.

## Practical rule

Do not rewrite the UI controller and the task runner protocol at the same time.
The controller is transport. Runner correctness and repository proof belong in the
runner/evidence contract.
