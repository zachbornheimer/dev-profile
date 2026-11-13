---
name: mise-dot-fleet-gotchas
description: "Before diagnosing or changing how dotfiles spread across the fleet (mise dot history, Relay/E2B boxes, VPS adopt/share, ~/.config/mise/config.toml tracked files), or when a box stays fetch-only, a tracked script loses +x, or a dev-profile fix does not reach boxes"
---

---
name: mise-dot-fleet-gotchas
description: "Before diagnosing or changing how dotfiles spread across the fleet (mise dot history, Relay/E2B boxes, VPS adopt/share, ~/.config/mise/config.toml tracked files), or when a box stays fetch-only, a tracked script loses +x, or a dev-profile fix does not reach boxes"
---

# mise dot fleet gotchas (verified 2026-11-11)

## Facts that cost hours
- **Exec bits (`+x`) are stripped only when `encrypt = true` (mise bug).** Unencrypted `mode = "track"` files preserve `100755` in the git tree (`dotfiles/reference.md:302-307`). However, `.mise-history/manifest.json` `.permissions` only records modes that are not `0644` or `0755`, relying on the git tree mode for `0755` — and mise's age encryption path writes encrypted blobs as `100644`, losing `+x` in both the tree and `.permissions`. Either omit `encrypt = true` on scripts that hold no secrets, or keep `chmod +x` in `[bootstrap.hooks.post-dotfiles]` and `[history.reload]` in `~/.config/mise/config.toml`.
- **Every container/VPS that gets dotfiles MUST have publishing rights.** Self-improvement requires boxes (Hetzner VPS, E2B, Docker) to publish dotfile improvements back to `zachbornheimer/dotfiles.git#history`.
- **`merge = true` sources win over the live file.** `~/.config/worktrunk/config.toml/dev-profile` merges `dev-profile/config/worktrunk.toml` over the tracked file on every bootstrap. An edit made only in the live file is dropped on every box, and the box then publishes that drop back to the fleet. Edit the dev-profile source.
- **dev-profile copies are not what boxes source.** `~/.profile` and `~/.config/ai/env.sh` are tracked separately (encrypted) in the mise history. Fixing `dev-profile/home/profile` or `apps/ai/env.sh` does not change them. Edit the live tracked file on the Mac and publish it.
- **Linux wedge (jdx/mise#15571).** A box's first apply touches about 2,700 paths. The checkpoint message passes Linux's 128 KiB per-argument limit (`Argument list too long (os error 7)`), and the operation stays pending forever. `tools/vps/adopt-dotfile-history.sh` `close_wedged_operations` now handles it; macOS cannot reproduce it.
- **Why a box stays fetch-only:** look for the `E2B-SESSION: prep: share: not the shared state: <reason>` line. The usual cause is the fleet publishing during the 10-minute ticket gate, which `take-shared` now covers.
- **Fixing the tailscale wrapper's +x made it run on boxes.** It joins the tailnet first, so the box's own `tailscale up` needs `--reset` (fix branch `fix/relay-tailnet-reset`, 2026-11-10).

## Publishing when the Mac's `mise dot sync` is locked
"another setup sync or pull is running" comes from `dev-profile-mise-history-watchdog` or `mise dot watch`. Do not kill them blindly. To publish urgently, build a commit on the origin `history` tip with `git commit-tree` in a bare clone and push it. Run the chain under `set -e` and never pipe a step into `tail` inside an `&&` chain: that hid a failed fetch and pushed an empty commit (`1eacab2`).

## Checks
- Origin tip: `git ls-remote https://github.com/zachbornheimer/dotfiles.git refs/heads/history`
- A box's diff: `mise dot history diff --patch --path <file>`. A raw `git diff` of the stored blobs is meaningless, because they are age-encrypted.
