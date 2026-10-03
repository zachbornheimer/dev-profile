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

That copies `profiles/personal.toml` to `~/Developer/Personal/mise.toml` and trusts it.

Design: `docs/01-tool-ownership.md` through `docs/12-not-rebuilt.md`.
