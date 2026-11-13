---
name: herdr-popup-stuck-oneshot
description: "herdr popup (prefix+!, oneshot.sh) blank/stuck or cannot be closed; how to close a popup via the socket API and the gotchas editing ~/.config/herdr/oneshot.sh"
---

## Facts (verified 2026-11-09)
- `prefix+!` runs `~/.config/herdr/oneshot.sh` as a herdr popup (config.toml `[[keys.command]] type="popup"`). The live file is `mise dot`-tracked (`mise dot history`), not the stale copy in dev-profile/apps/herdr.
- Popups do NOT appear in `herdr pane list` / `api snapshot`. Close a stuck one by sending `{"id":"x","method":"popup.close","params":{}}` as one JSON line to the unix socket `~/.config/herdr/herdr.sock` (default session; `sessions/<name>/herdr.sock` for others). Python `socket.AF_UNIX` one-liner works; reply `{"result":{"type":"ok"}}`.
- Blank popup cause: the script used to run `reap` + `respawn_pending` (walks every tracked tab via herdr API + hashing) BEFORE asking questions. Now questions come first and housekeeping runs detached via `oneshot.sh --respawn` with a `.housekeeping.lock` dir. Hashing uses `cksum` (macOS `shasum` is perl and is very slow under load).
- Popup flow is pages (prompt, 1-shot?, target, model) driven by `ask_*` functions; non-zero gum exit (esc/ctrl+c) = back one page, esc on page 1 exits. ONESHOT_* env hooks remove pages.
- Test without a tty: put stub `gum` (scripted answers, exit 130 = esc) and stub `herdr` on PATH, set `HERDR_BIN_PATH`, `ONESHOT_DIR`, `ONESHOT_SESSION=test`.

## Gotchas
- The `edit`/`edit_replace` tools rewrite oneshot.sh WITHOUT the exec bit; run `chmod +x ~/.config/herdr/oneshot.sh` after every edit or the popup dies with "Permission denied".
- `mise dot save` can fail with "another history operation is running"; the watcher saves anyway.
- Do not report machine load numbers to the user (user rule).
