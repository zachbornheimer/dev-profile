---
name: mise-bootstrap-unknown-field-warnings
description: "Fix mise WARN \"unknown field\" messages for [bootstrap.*] keys in ~/.config/mise/config.toml (e.g. bootstrap.symlinks, bootstrap.repos.*.sync)."
---

# Fixing mise bootstrap unknown-field warnings

Verified on mise 2026.11.5 (docs: mise.jdx.dev/bootstrap, /bootstrap/repos.html, /dotfiles/managed.html).

- `[bootstrap.symlinks."<path>"]` (target/os) does not exist. Use `[dotfiles."<path>"]` with `source`, `mode = "symlink"`, and `variants = [{ os = "linux" }]` for OS gating.
- `[bootstrap.repos."<path>"]` accepts only `url`, optional `ref`, and clone options `filter`, `depth`, `submodules`. No `sync` key: delete it. With no `ref`, `mise bootstrap --update` fast-forwards a clean checkout.
- Edit the file with the `edit` tool (config is mise-dot tracked, not a git repo).

Verify: `mise bootstrap status`, `mise dot apply --dry-run`, `mise dot diff` show no WARN.
`mise bootstrap repos apply` refuses dirty checkouts; `--skip-dirty` skips them. Do not commit others' dirty changes.
