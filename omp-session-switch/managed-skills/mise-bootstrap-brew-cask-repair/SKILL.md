---
name: mise-bootstrap-brew-cask-repair
description: "Fix mise bootstrap packages status/apply aborting on brew-cask errors (only script installers supported / manual installer casks, stale Caskroom metadata, multiple versions, pkg casks) and defaults gotchas."
---

# mise bootstrap: brew-cask status & apply repair

`mise bootstrap packages status` and `apply` stop at the FIRST bad cask, so loop or scan all declared casks at once.

## Error -> fix
- `brew-cask: only script installers are supported` (`crates/mise-brew-metadata/src/cask/artifacts/ordinary.rs`):
  - Cause: a declared cask not yet in `/opt/homebrew/Caskroom` uses Homebrew's `installer manual:` stanza (e.g. `brew-cask:license-control-center` -> `{"installer": [{"manual": "eLicenserControlSetup.app"}]}`). Already-installed casks short-circuit on Caskroom presence, so the source Mac won't hit this until a fresh Mac tries to plan the install, where one `manual` cask aborts the entire `brew-cask` batch.
  - Find all offending casks at once:
    `python3 -c 'import json,re,pathlib,subprocess; casks=re.findall(r"\"brew-cask:([^\"]+)\"", pathlib.Path("~/.config/mise/config.toml").expanduser().read_text()); out=subprocess.check_output(["brew","info","--cask","--json=v2",*casks]); print([c["token"] for c in json.loads(out)["casks"] for a in c.get("artifacts",[]) if isinstance(a,dict) and "installer" in a and any("manual" in x for x in a["installer"])])'`
  - Fix: remove the `installer manual:` cask from `[bootstrap.packages]` in `~/.config/mise/config.toml`, or pre-populate `/opt/homebrew/Caskroom/<cask>` on the target machine via `brew install --cask <cask>`.
- `Homebrew metadata exists, but no installed Caskroom version was found` : `/opt/homebrew/Caskroom/<cask>` holds only `.metadata`.
  - Find all at once: `cd /opt/homebrew/Caskroom; for d in *; do [ -z "$(ls "$d" | grep -v '^\.metadata$')" ] && echo $d; done`
  - Fix: `brew reinstall --cask --force <cask...>` (overwrites the app in place).
  - If it fails with "already a Binary at /opt/homebrew/bin/X": the tool self-installed; `mv` it to /tmp/X.bak, then reinstall.
  - pkg-installer casks (e.g. filebot) purge the Caskroom dir after install, so mise can never track them: remove from `[bootstrap.packages]`.
- `multiple Caskroom versions (a, b)`: `rm -rf /opt/homebrew/Caskroom/<cask>/<old-version>`. A `latest` symlink beside one version dir is normal.

## Defaults gotchas (`[bootstrap.macos.defaults.*]`)
- Values are NOT templated: `{{ env.HOME }}` stays literal. Use `~/...` (screencapture accepts it).
- Dock `tilesize`/`largesize` are stored as reals; declare `43.0`, not `43`, or status shows drift.
- `persistent-apps` must list only apps that exist on a fresh Mac; custom/unsigned apps (not in any cask/MAS) cannot be declared and will be dropped from the Dock on apply.
- Check drift: `mise bootstrap macos defaults status | awk '{print $1,$2,$NF}' | grep -v ' set$'`; preview writes with `apply --dry-run`.

## Workflow
Edit in a worktree (`wt switch -c`), `mise trust` the worktree, commit with a conventional subject of 60 chars or fewer (hk hook enforces), land with `wt merge -y main`.
