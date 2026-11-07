# omp custom build: build once in CI, install everywhere with mise

Accepted 2026-11-02 (user: "perfect. please proceed with this approach").

## Goal

One custom `omp` = fork `main` (upstream `can1357/oh-my-pi` main plus one carry commit holding the build machinery:
`.github/workflows/omp-build.yml` and `.omp-build/`) + the topic branches listed one TOML file each under
`.omp-build/branches/`, built once in GitHub Actions on `zachbornheimer/oh-my-pi`, installed on the MBP and every
fleet machine by mise. `main` is the default branch; there is no `ci` branch and no pin file.

Revised 2026-11-06 (user: "we should not pin upstream, it should use our main"): the earlier design pinned a
40-hex upstream SHA on a `ci` branch. Replaced by: base = the triggering commit (fork `main` tip), advanced only by
merging upstream (`scripts/sync-fork-main.sh`). Cut over to carry-on-main the same day: the workflow, the resolver
(`.omp-build/resolve-branches.ts`) and the branch files live on `main`; `ci` and `carry/omp-build` are deleted; the
130 `tools/*` branches left the fork for the private repo `zachbornheimer/omp-tools`.

## Contract

- Workflow: `.github/workflows/omp-build.yml` on the fork's default branch `main`, `schedule` hourly at minute 17 +
  `workflow_dispatch` (input `branches_override`: comma list; non-empty publishes a prerelease only).
- Branch list: one file per branch under `.omp-build/branches/` (path minus `.toml` is the branch name); fields
  `reason`, `upstream` = no|candidate|submitted|merged, `pr`, `layer` (default 50); order is (layer, path).
- Assembles `omp-build` from the triggering commit (fork `main` tip) + listed branches. Any conflict: fail, publish
  nothing, open/update one `omp-rebuild` issue per branch naming the files. Previous release stays `latest`.
  An assembled tree identical to the latest release's build commit skips build and release.
- Release: tag `build-<YYYYMMDDHHMMSS>-<upstream-short-sha>-<build-short-sha>`, where the middle field is the newest
  upstream commit contained in `main`, marked latest. Assembly computes the
  tag and bakes it into both binaries (`PI_BUILD_IDENTITY`), so `omp --version` prints `omp/<semver>` then
  `github.com/zachbornheimer/oh-my-pi@<tag>`, and the welcome banner shows that identity as its version label.
  Assets: `omp-darwin-arm64.tar.gz`, `omp-linux-x64.tar.gz` (each containing a single `omp`), plus `SHA256SUMS`.
- Install: global mise config `"github:zachbornheimer/oh-my-pi" = { version = "latest", matching = "omp-", minimum_release_age = "0" }`
  (`matching` keeps the `omp-` tarballs and drops `SHA256SUMS`; `bin` would imply a single-file download — wrong for tarballs;
  `minimum_release_age = "0"` because the fork's own CI builds each release — the 24h default would hide every daily build until the next).
- Stable entrypoint `~/.local/bin/omp` → the mise shim, created idempotently on every machine by
  `bin/dev-profile-omp-machine-setup` (`mise run setup`): consumers whose PATH has `~/.local/bin` without the shims dir
  (the capability gateway shells out to plain `omp`) depend on it. Never delete it.
  Verify: `env -i HOME=$HOME PATH=$HOME/.local/bin:/usr/bin:/bin ~/.local/bin/omp --version` — two lines: `omp/<semver>`
  then the release identity `github.com/zachbornheimer/oh-my-pi@<tag>`.
- Daily `mise up github:zachbornheimer/oh-my-pi` through `bin/dev-profile-omp-sync`: macOS LaunchAgent `dev.mise.omp-daily-sync`, Linux systemd `omp-daily-sync.timer`. The script drops mise's cached "latest release" response first (a release published minutes ago is otherwise invisible for the cache's lifetime), then fails unless `omp --version` names the version `mise current` reports.

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

- `steering-fixes` is still one stack of branches, not split into independent branches based on `main`.
- Twelve branches carry `upstream = "candidate"`: they have not yet been rebuilt as PR-clean branches off
  `upstream/main` and submitted.
- Custom omp tools are in the private repo `zachbornheimer/omp-tools` (`.omp/tools/<name>`); omp loads custom tools
  from `~/.omp/agent/tools` or `.omp/tools`, and they are not yet installed there.
