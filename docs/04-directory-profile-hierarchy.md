# 4. Directory / profile hierarchy (this machine)

The objective's sketch `~/Developer/{Company,Freelance,Personal}` is not this disk.

## Live roots

| Role      | Path                                       | Status                                                                    |
| --------- | ------------------------------------------ | ------------------------------------------------------------------------- |
| Personal  | `~/Developer/Personal`                     | Real. Git checkouts live here (agentmux, attention-mail, zq, dotfiles, …) |
| Company   | `~/Developer/Software-Automation-Holdings` | Real. Do not rename to `Company`                                          |
| Freelance | —                                          | Absent. Do not create a folder to match the sketch                        |
| Base      | `~/.config/mise/config.toml`               | Global. Chezmoi-managed                                                   |

`~/Developer` also contains other trees (Zysys, ninja-quoter, artifacts, …). Those are not profile roots.

## How selection works

mise walks parent directories and merges. Closer files override.

```
~/.config/mise/config.toml          # base tools (global)
~/Developer/Personal/mise.toml      # personal overlay  ← phase 1
~/Developer/Personal/<repo>/mise.toml   # repo deltas only
```

There is **no** `~/Developer/Software-Automation-Holdings/mise.toml` in phase 1. A SAH checkout therefore sees global + its own repo file, not the Personal overlay.

There is no `profile company` command. `cd` is sufficient.

## Marker

Personal overlay exports `DEV_PROFILE=personal` via `[env]`. Tests call real `mise env` / `mise config ls` from a Personal git root and from `~/Developer/Software-Automation-Holdings/dev-config`. No `profile` argv.

## What a repository should contain

Only genuine deltas (language pins, tasks). attention-mail already has `fmt` and `test`. Do not copy formatter/tool policy into ~70 SAH repos. Company shared policy later belongs in an SAH parent file or `git::` include, not phase 1.

`~/Developer/Software-Automation-Holdings/dev-config` is the company platform repo. It is a consumer of company policy, not the Personal Dev Profile.
