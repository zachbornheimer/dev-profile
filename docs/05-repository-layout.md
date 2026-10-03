# 5. Dev Profile repository layout

This repository is `~/Developer/Personal/dev-profile`. It is the version-controlled source of truth for profile files and the twelve design artifacts. It is **not** a new orchestration binary.

```
dev-profile/
├── README.md
├── mise.toml                 # fmt / test / install-profile for this repo
├── go.mod
├── profile_test.go           # drives live mise + zq
├── .gitignore                # allowlist
├── docs/
│   ├── 01-tool-ownership.md
│   ├── …                     # through 12-not-rebuilt.md
└── profiles/
    ├── base.toml             # documents global base; not installed as a parent in phase 1
    └── personal.toml         # copied to ~/Developer/Personal/mise.toml
```

## Include model (later)

mise `include = ["git::https://github.com/zachbornheimer/dev-profile.git//profiles/personal.toml?ref=main"]` can replace the copy once the remote exists. Phase 1 uses a local copy so `cd` works offline and does not fetch on untrusted config.

dprint Wasm policy can live here and be remote-extended. Exec plugin mappings cannot: they stay in a locally installed trusted file (artifact 7).

## What stays out

Chezmoi still owns `~/.config/mise/config.toml` and zsh. This repo does not take over dotfiles in phase 1.
