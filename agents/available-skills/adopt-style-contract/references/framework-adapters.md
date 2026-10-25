# Framework adapters

The contract is the vocabulary; the framework gets an adapter that translates
it. Never edit the framework's own token names, and never let the adapter
become the source of truth.

## Tailwind v4

Two `@theme` blocks. Any theme key whose NAME equals a contract token
(`--color-ink`, `--color-brand`, `--color-border`, `--color-error`,
`--color-warning`, `--color-success`) must go in `@theme reference`.
Plain `@theme` and `@theme inline` both emit an unlayered `:root` bootstrap
`--color-ink: var(--color-ink)`, a self-reference cycle that outranks
`@layer whitelabel` and falls back to the `@property` initial value, so
brand overrides silently stop working. `reference` emits no `:root`
variables; utilities still compile to `var(--color-ink)` and resolve to
the contract/whitelabel declaration.

```css
@theme reference {
  --color-ink: var(--color-ink);
  --color-brand: var(--color-brand);
  --color-border: var(--color-border);
}

@theme {
  --color-page: var(--color-page-background);
  --color-action: var(--color-primary-action);
  --font-heading: var(--font-family-heading);
  --radius-md: var(--corner-radius);
}
```

Keys with a different name than their contract source stay in plain
`@theme` (no cycle). Theme-only roles with no other source (`--color-fill`)
must stay in plain `@theme` or they vanish under `reference`. Grep the
built CSS for `--color-\w+: var(--color-\w+)` self-references after the
build; zero is the pass condition.

## Tailwind v3

`tailwind.config.js` theme values as `"var(--color-brand)"` strings. Colors
need `<alpha-value>` handling: `"rgb(from var(--color-brand) r g b / <alpha-value>)"`.

## Bootstrap 5

A bridge file loaded after Bootstrap and the contract:

```css
:root {
  --bs-body-bg: var(--color-page-background);
  --bs-body-color: var(--color-ink);
  --bs-primary: var(--color-primary-action);
  --bs-link-color: var(--color-brand);
  --bs-border-color: var(--color-border);
  --bs-border-radius: var(--corner-radius);
  --bs-body-font-family: var(--font-family-body);
}
```

Bootstrap also bakes `--bs-primary-rgb`; set it with
`rgb(from var(--color-primary-action) r g b)` channels or accept that
`.bg-primary` opacity utilities stay unbranded, and say which.

## Plain CSS / CSS Modules

No adapter. Components read contract tokens directly after the replace phase.

## CSS-in-JS

Theme object values become `"var(--color-brand)"` strings. Do not read the
contract at build time into literals; that freezes the brand.
