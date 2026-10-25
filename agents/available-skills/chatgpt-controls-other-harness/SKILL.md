---
name: chatgpt-controls-other-harness
description: >-
  Provider-agnostic ChatGPT desktop controller. Downloads the newest
  run-<uuid>.py/.zip from View files in chat, runs PROVIDER=<cli> uv run --
  <runner>, and pastes evidence only after the composer Stop square becomes
  Send. Use for one-shot ChatGPT→harness loops (grok, claude, …).
---

# ChatGPT → other harness

`PROVIDER` is required. Missing it is a hard error. It is the CLI name on PATH.

```bash
PROVIDER=grok python3 controller/agentmux-autoloop-v9.py --once
PROVIDER=claude python3 controller/agentmux-autoloop-v9.py --once
```

`--once` (the mode to use): close/reopen Files in chat, take the **bottom**
newest unmatched `run-<uuid>.*`, wait for the preview **Download** button,
save to `~/Downloads`, execute, wait until the composer **Stop** control is
gone and **Send** is back, paste the evidence zip, exit.

```bash
PROVIDER=grok uv run -- ~/Downloads/run-<uuid>.py
PROVIDER=grok uv run python ~/Downloads/run-<uuid>.zip   # zipapp with __main__.py
```

A zip that only wraps a `run-*.py` is extracted, then `uv run --` on that py.

Do not start the infinite loop unless asked. Kill any running controller
before editing this skill.
