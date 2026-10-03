# Dev Profile

Version-controlled personal development profile. Not an orchestration tool.

`cd` into a git checkout under `~/Developer/Personal` selects this overlay. There is no `profile` command.

```
mise run fmt
mise run test
```

are the canonical commands. Agents do not pick npm, pnpm, aube, uv, or Composer.

Install the overlay on this machine:

```
mise run install-profile
```

That copies:

- `profiles/personal.toml` → `~/Developer/Personal/mise.toml` (trusted)
- `format/personal.jsonc` → `~/Developer/Personal/dprint.jsonc`
- `worktrunk/config.toml` → `~/.config/worktrunk/config.toml`

This repo's `mise run fmt` is `dprint fmt`. attention-mail keeps its own `fmt` and `test`.

Design: `docs/01-tool-ownership.md` through `docs/12-not-rebuilt.md`.
