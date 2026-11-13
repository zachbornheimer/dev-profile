---
name: mise-adopt-second-machine-gotchas
description: "Gotchas when running mise bootstrap --adopt zachbornheimer/dotfiles (history branch) onto a second Mac such as the mini; covers branch choice, age recipients, replace-history adopt, conflicts, plaintext-history guard, APFS snapshots, brew-cask failures, mas/Spotlight/NFS hangs, Dock entries, post-reboot Tailscale SSH check, and launchd trimming."
---

Learned adopting dotfiles onto the Mac mini (2026-11-10/11, mise 2026.11.5-6). Remote mini has old mise; use `mise bootstrap remote --host mini --adopt ... --install-mise`.

## Adopt mechanics (verified)
1. Adopt the `history` branch, not main: `--adopt 'zachbornheimer/dotfiles?ref=history'`. `main` is the legacy chezmoi tree; a plain `mise bootstrap --adopt zachbornheimer/dotfiles` clones it into ~/.config/mise. Undo: move ~/.config/mise aside, restore config.toml, config.local.toml and age.txt (the mini kept copies in ~/.config/mise_).
2. Encrypted files need the new machine's age public key as a recipient BEFORE pull: `mise exec age@latest -- age-keygen` on the new machine, add to `history.encryption` recipients on the MBP, `mise dot save --re-encrypt` + `mise dot sync`.
3. Every `source` path the config declares must exist on the new machine (dev-profile, dev-env under ~/Developer/Personal). Move a stray non-git dir aside first.
4. Plain `--adopt` on a machine with prior local history failed `invalid or unenrolled permission path config/config.toml` (cause not found). What worked: `--adopt 'zachbornheimer/dotfiles?ref=history' --replace-history --take-remote-all --yes` with env MISE_HISTORY_ALLOW_PLAINTEXT_HISTORY=1. Back up ~/.local/state/mise/history first.
5. `--replace-history` refuses with `could not save this machine's version of <path> before replacing it`, one file per run (minutes each). Move aside ALL files that changed on origin since the machine's last pull (`git diff --name-only <upstream_commit from sync.json>..origin/history -- home config`) in one step into ~/.pre-adopt-backup-<date>/moved-aside/, then run once.
6. Origin `history` is also written by `mise@e2b.local` relay boxes, so its tip moves mid-adopt. `--allow-plaintext-history` is a `sync` flag; for pull/bootstrap use env MISE_HISTORY_ALLOW_PLAINTEXT_HISTORY=1 for that run only.
7. Empty `~/.agents` dir blocks the symlink: `rmdir` it. Bootstrap runs `repos` before `dotfiles`; the restored gitconfig sets core.hooksPath to ~/.agents/hooks so clones fail with exit 127. Run `mise bootstrap --only dotfiles --yes` first.
8. `mise trust` ~/Developer/Personal/dev-profile/config and ~/Developer/Personal.
9. Dock: `[bootstrap.macos.dock].apps` fails the whole bootstrap for any app not installed (`Dock application is unavailable: ...`). Remove a cask's Dock line in the same change. mas apps (iReal Pro) exist only after mas installs them.
10. Publishing a config fix when the MBP `mise dot save/sync` fails with `another history operation is running`: clone origin `history` shallow into /tmp, edit config/config.toml, commit, `git push origin HEAD:history` (worked for the Dorico Dock fix, commit 4a55f2b). The MBP then merges on its next pull. On a loaded MBP git fetch/push can exceed 5 min: run it as a background job and yield, do not poll.

## Reboot / SSH
11. After a mini reboot, Tailscale SSH demands a browser re-auth (`# Tailscale SSH requires an additional check. visit https://login.tailscale.com/a/...`); until the user approves, every ssh silently stalls to timeout. Also /tmp is wiped, so scripts copied earlier are gone.

## mas / Spotlight / NFS (verified)
12. `mas list --json` needs a signed-in App Store AND working Spotlight. The mini's `mds` sat in state `U` for 4 days on the NFS mount `192.168.1.99:/volume1/Zach Mac File Share` at `/Volumes/Zach Mac File Share` (mounted by org.zysys.nas-mount with options `hard,intr`; NAS itself reachable). `umount -f`, `diskutil unmount force`, `lsof`, `mdutil -i on /` and `dd` all hang uninterruptibly. Symptom: bootstrap hangs re-spawning `mas list`; gpg-suite and microsoft-teams pkg scripts hang on mdfind. A reboot cleared it (mini: FileVault off, autologin on); after reboot Spotlight indexing was enabled and mas installs ran. `hard` NFS mounts are the likely root cause (unverified); consider `soft` options.
13. While mas is unusable: `mise bootstrap --skip packages,tools --yes` (the post-tools hook also calls mas).
14. Xcode (mas:497799835) is queued first of 29 mas apps; the mini had only ~20 GB free, so watch disk.
15. Mini keychain prompt: stale `librarian-codesign.keychain-db` default. `security default-keychain -d user -s login.keychain-db`, `security list-keychains -d user -s login.keychain-db`, move file aside, `pkill -x SecurityAgent`.

## brew-cask on a new Mac (verified)
- `brew-cask: only script installers are supported`: one `installer manual:` cask (license-control-center) aborts the batch. Find via `brew info --cask --json=v2 <casks>` `artifacts[].installer`.
- ENOSPC: purgeable Time Machine local APFS snapshots (`diskutil apfs listSnapshots disk3s5`, `deleteSnapshot ... -uuid`), old /opt/homebrew/Cellar versions, ~/Library/Caches/mise/system-brew/casks and downloads-cas/blobs.
- `.pkg` casks need /usr/sbin on PATH for sudo (`ln -sf /usr/sbin/installer /opt/homebrew/bin/installer`).
- gcloud-cli postflight on macOS 26.0.1: Homebrew Python pyexpat can't load /usr/lib/libexpat; install Homebrew expat, install_name_tool + codesign, then `PIP_REQUIRE_VIRTUALENV=0 pip install --break-system-packages virtualenv`.
- onyx: DMG license rejects `hdiutil attach -quiet`; ngrok, raycast, steam: copy Caskroom/<tok> + app from MBP via tar over ssh.

## launchd trimming on the mini (done 2026-11-11)
Mini startup set = ~67 non-Apple plists, only dev.mise.mise-history and dev.herdr.tab-titles are in mise. Removed by bootout + mv to ~/.launchd-removed-20261111/: agentmux-node/plane, homebrew mariadb/mysql/supervisor, OneDrive (+app), Java updater/helper, Docker socket/vmnetd (Colima only), Wireshark ChmodBPF, AFP mounter com.local.mount_zach_share (kept org.zysys.nas-mount NFS). `launchctl bootout` can need a second try (supervisor). ~38 org.zysys.* homelab daemons remain and fit a mini-only bootstrap launchd group. Adobe/Zoom/ScanSnap/MacPorts/local.wait.w-* jobs exist only on the MBP.
