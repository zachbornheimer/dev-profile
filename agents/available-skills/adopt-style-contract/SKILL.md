---
name: adopt-style-contract
description: Use when adding style-contract tokens to a new app, migrating an existing app onto them, or refreshing the vendored snapshot after a contract change.
---

# Adopt style contract

Canonical source is the `style-contract` package (`tokens.json` + generator).
This skill vendors a snapshot in `references/contract/`. Other repos copy
those files. They never regenerate.

## Which file

| Host                               | Copy from `references/contract/`                               |
| ---------------------------------- | -------------------------------------------------------------- |
| Can use `@layer`                   | `contract.gen.css` (no order list) from `references/contract/` |
| Unlayered vendor CSS (WP, Kadence) | `contract.gen.legacy.css`                                      |
| Brand overrides                    | `brand.example.css`                                            |

Host owns the layer list. Insert `contract` before kit and whitelabel:

```css
@layer reset, …, contract, kit, whitelabel, app;
```

Do not put `@layer contract.defaults, whitelabel;` in the contract file —
if the host already named `whitelabel`, that statement appends `contract`
after `app` and defaults beat brand.

If the host already wraps brand CSS in `@layer whitelabel`, delete the
unlayered fallback `:root` at the bottom of `brand.example.css`. Two
uncommented copies let the unlayered block beat `@layer app`.

## Three SHAs

| Mismatch                             | Meaning                          | Action                                                                                                                                                                                           |
| ------------------------------------ | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| package `dist/` vs this snapshot     | skill is stale                   | `node ~/.agents/available-skills/adopt-style-contract/scripts/refresh-from-package.mjs <path/to/style-contract>` then `chezmoi add --recursive ~/.agents/available-skills/adopt-style-contract/` |
| snapshot `shas.json` vs itself       | snapshot corrupted               | re-run refresh                                                                                                                                                                                   |
| snapshot vs the app's `contract.css` | app drifted or contract upgraded | **copy** from `references/contract/` — do not regen in the app                                                                                                                                   |

`scripts/check-snapshot.mjs` verifies the snapshot against `shas.json`.
`scripts/install-into-repo.mjs <repo> [--legacy]` copies the matching pair
into `styles/` (or `--out-dir`).

Greenfield: answer `references/host-inventory.md` from the target repo,
then install, insert the `contract` slot, uncomment brand tokens, commit
the copied CSS plus the snapshot SHA. App CI hashes `contract.css` against
that SHA. Do not special-case a repo; the inventory picks the file.

## Migrate an existing app

Five phases. Human approves the mapping table before any edit. Computed-style
snapshot identical after every editing phase. Read token descriptions from
`references/contract/contract.json`, not from memory.

### Phase 1 — Inventory (read-only)

`docs/style-contract/inventory.md`: tokens, framework, layers. Queries in
`references/inventory-queries.md`. Layer/wrap questions in
`references/host-inventory.md`. Stop if the app has more than one root
token file.

### Phase 2 — Mapping

`docs/style-contract/map.md` from `references/map-template.md`. Columns:
becomes contract token / derives from contract / stays private. Never invent
a public token. **Gate:** present the table and stop.

### Phase 3 — Shim

Snapshot (`references/snapshot.md`). Load `contract.gen.css` (or legacy)
before the app token file. Rewrite the app token file: `--old: var(--contract)`
for "becomes" rows. Re-snapshot; empty diff.

### Phase 4 — Replace

Script-rename `var(--old)` to `var(--contract)` for "becomes" rows. Drop
shims. Adapters: `references/framework-adapters.md`. Re-snapshot; empty diff.

### Phase 5 — Layers

Adopt `@layer` only when no unlayered third-party CSS must beat the app.
Otherwise write `docs/style-contract/layers.md` and stop. When it passes,
the **host** lists `contract` then `whitelabel` then `app`. Do not add an
order statement to the contract file.

## Done

- Snapshot SHA in the app matches `references/contract/shas.json`
- Mapping approved; snapshots identical
- `mise run ci` (or the repo gate) green
- Uncommenting one token in the brand file changes the page
