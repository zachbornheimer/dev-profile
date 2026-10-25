# Token map — <app name>

Contract version: <header line from contract.css>
Inventory: docs/style-contract/inventory.md

## Becomes a contract token

| app token       | contract token            | conversion      | notes                                              |
| --------------- | ------------------------- | --------------- | -------------------------------------------------- |
| `--color-paper` | `--color-page-background` | none            | app used one white for page and cards              |
| `--space-unit`  | `--spacing`               | ×6 (4px → 24px) | kit-private scale; public token is the section gap |

## Derives from contract

| app token       | formula after shim                                | replaces          |
| --------------- | ------------------------------------------------- | ----------------- |
| `--color-muted` | `oklch(from var(--color-ink) calc(l + 0.29) 0 0)` | literal `#6b6b6b` |

## Stays private

| app token           | why                                      |
| ------------------- | ---------------------------------------- |
| `--hero-min-height` | component geometry, not a brand decision |

## Not expressible (report to contract owner)

| app need | closest contract token | gap |
| -------- | ---------------------- | --- |
