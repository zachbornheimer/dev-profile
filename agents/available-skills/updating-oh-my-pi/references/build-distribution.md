# omp custom build: build once in CI, install everywhere with mise

Accepted 2026-11-02 (user: "perfect. please proceed with this approach").

## Goal

One custom `omp` = upstream `can1357/oh-my-pi` main + the topic branches listed in the fork's
`.github/omp-rebuild.toml` (branch `ci`), built once in GitHub Actions on `zachbornheimer/oh-my-pi`,
installed on the MBP and every fleet machine by mise. `main` stays a pure upstream mirror.

## Contract

- Workflow: `.github/workflows/omp-build.yml` on the fork's default branch `ci` (scheduled workflows only run
  from the default branch; `main` stays the mirror), `schedule` daily 04:00 UTC + `workflow_dispatch`
  (input `branches_override`: comma list, empty string = no branches).
- Assembles `omp-build` from upstream main + listed branches. Any conflict: fail, publish nothing,
  open/update one GitHub issue naming the branch and files. Previous release stays `latest`.
  An assembled tree identical to the latest release's build commit skips build and release.
- Release: tag `build-<YYYYMMDD>-<upstream-short-sha>-<build-short-sha>`, marked latest.
  Assets: `omp-darwin-arm64.tar.gz`, `omp-linux-x64.tar.gz` (each containing a single `omp`), plus `SHA256SUMS`.
- Install: global mise config `"github:zachbornheimer/oh-my-pi" = { version = "latest", matching = "omp-", minimum_release_age = "0" }`
  (`matching` keeps the `omp-` tarballs and drops `SHA256SUMS`; `bin` would imply a single-file download — wrong for tarballs;
  `minimum_release_age = "0"` because the fork's own CI builds each release — the 24h default would hide every daily build until the next).
- Stable entrypoint `~/.local/bin/omp` → the mise shim, created idempotently on every machine by
  `bin/dev-profile-omp-machine-setup` (`mise run setup`): consumers whose PATH has `~/.local/bin` without the shims dir
  (the capability gateway shells out to plain `omp`) depend on it. Never delete it.
  Verify: `env -i HOME=$HOME PATH=$HOME/.local/bin:/usr/bin:/bin ~/.local/bin/omp --version`.
- Daily `mise up github:zachbornheimer/oh-my-pi`: macOS LaunchAgent `dev.mise.omp-daily-sync`, Linux systemd `omp-daily-sync.timer`.

## Removed after cutover (done 2026-11-02)

- `bin/dev-profile-omp-sync`, `config/omp-rebuild.toml`, `tests/omp-sync-fixture.sh` deleted from dev-profile; the
  main-lock reference-transaction hook survives inside `bin/dev-profile-omp-machine-setup` (run by `mise run setup`),
  which also creates the stable entrypoint.
- Fleet symlink `~/.local/bin/omp -> ~/Developer/Personal/oh-my-pi/...` (source-checkout target) replaced by the stable
  entrypoint above. dev-env `tools/vps/vps-up.sh` no longer builds/installs omp per box; its `vps:up` warm-gate checks
  both `~/.local/bin/omp` and the mise shim.
- `omp.url` pin + `nix/modules/omp.nix` in dev-env: KEPT — `checks/container.ts` runs `omp --version` inside the
  docker image built from the flake, which reaches omp only via `programs.omp`.

## Open

Five listed branches conflict with current upstream (a stack topped by `feat/browser-aria-ref-delegation`, plus
`omp-neon-sessions`); tracked in ZYS-2206 and fork issue #1. Until it lands, releases contain no custom branches.
