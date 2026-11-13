---
name: dev-env-vps-shell-tests
description: "Writing or running bash tests under dev-env/tests/vps_*.sh and landing vps tooling changes (provision marker, warm gate, vps-up reboot skip)"
---

# dev-env vps shell tests

- Tests live in `tests/vps_*.sh`, wired as `test:vps-*` tasks in `mise.toml`. Run one with `bash tests/<name>.sh`; the last line is `PASS: ...`.
- A test that sources `tools/vps/vps-up.sh` or runs `tools/vps/provision-marker.sh` MUST set `export PATH="/usr/bin:/bin:/usr/sbin:/sbin"` after setting a temp `HOME`. Otherwise a mise shim ahead of `/usr/bin` reads the real user's untrusted `~/.config/mise/config.local.toml`, prints "not trusted" errors, and the marker comes back empty.
- `provision-marker.sh` prints `v2:<sha256>` over `tools/vps`, `security/rules/typescript.yml`, the neovim pin and the dev-profile git revision. `mise.toml` edits must not move it. Tests assert the `v2:` prefix.
- `vps-up.sh` skips provisioning on a reused box whose marker matches after the tailnet join (it redoes only the tailnet join and the boot refresh); `VPS_FORCE_PROVISION=1` forces the full pipeline. The test fakes the box with a `vps_ssh` stub keyed on the command text.
- Writing a script with the `write` tool drops its executable bit; run `chmod 755` before committing.
- Land with `wt step commit` (hk hooks run, so it can take over 20 s and gets promoted to a background job) then `wt merge -y main`. `mise run lint` fails on darwin here because aqua `navi` and `upx` are unsupported; that is environmental.
