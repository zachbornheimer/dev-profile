# Controller

`agentmux-autoloop-v9.py` is included as the current known-good macOS ChatGPT
desktop transport controller.

The controller is **transport automation**, not the planner and not the repository
verifier.

## Contract

It:

- requires `PROVIDER` (`PROVIDER=grok` / `PROVIDER=claude`); exits if unset;
- closes Files in chat if it is already open, then opens it via More → View files in chat;
- takes the newest unmatched `run-<uuid>.*` (`FILES_LIST_NEWEST`, currently `"top"`);
- skips a filename that already exists in `~/Downloads`;
- saves via the native Save panel, or treats a new file in `~/Downloads` as success;
- executes `run-<uuid>.py` as `PROVIDER=<name> uv run -- <runner>`;
- executes `run-<uuid>.zip` as `PROVIDER=<name> uv run python <runner>`;
- refuses an already-processed UUID;
- ensures a `<uuid>.zip` evidence artifact exists;
- focuses the same ChatGPT conversation;
- pastes the ZIP and sends it;
- waits before looking for the next runner.

## Requirements

- macOS
- ChatGPT desktop app
- Accessibility permission for UI scripting
- `osascript`
- `uv`

## Do not change casually

The v9 controller deliberately avoids recursively crawling the full Accessibility
tree because that previously hung.

The proven strategy is a bounded Accessibility walk of More → View files in chat, not Tab-from-composer and not `entire contents`.

## Known caveat

The controller sends Enter and then retries Enter after five seconds. That can create
a duplicate attachment/send in some UI states. The loop works, but this should be
hardened separately from task-runner changes.

## State

Controller state/logs are stored under:

```text
~/.agentmux-autoloop-v9/
```

The controller currently expects files named:

```text
run-<uuid>.py
```

and evidence named:

```text
<uuid>.zip
```
