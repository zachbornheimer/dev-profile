# Style contract

Generated from `tokens.json`. Regenerate: `node src/build.mjs`.

## Load order

The host owns the cascade-layer list. Declare it once, before any of these sheets:

```css
@layer reset, contract.defaults, kit, whitelabel, app;
```

`contract.gen.css` registers unlayered `@property` rules and assigns defaults inside `@layer contract.defaults`. It does **not** declare the layer-order list — if it did, a host could not place `app` after `whitelabel`. Load it (or `contract.min.css`) before any `@layer whitelabel` override.

`dist/brand.example.css` ships both a layered `@layer whitelabel` block and an unlayered `:root` fallback. Delete the fallback if the host already wraps the file in `@layer whitelabel`.

Hosts that cannot use cascade layers should load `contract.gen.legacy.css` (or `contract.min.legacy.css`) instead: the same `@property` registrations plus unlayered `:root` defaults. A later unlayered `:root` override still wins.

## Dark mode

No dark-mode tokens ship. Override the base colors under `:root[data-theme="dark"]` inside `@layer whitelabel`; `--color-border`, `--color-page-accent`, the header/footer tokens, and `--color-primary-action` all derive from these and follow automatically. `--color-brand` is optional.

```css
@layer whitelabel {
  :root[data-theme="dark"] {
    --color-page-background: #121212;
    --color-surface: #1e1e1e;
    --color-ink: #f2f2f2;
  }
}
```

This contract deliberately does not ship `prefers-color-scheme` or `light-dark()` defaults — dark mode is opt-in via `data-theme`.

## Page

| Name                    | Type    | Default   | Derived from                                                             | Minimum | Description                                                            | Uses                                |
| ----------------------- | ------- | --------- | ------------------------------------------------------------------------ | ------- | ---------------------------------------------------------------------- | ----------------------------------- |
| --color-page-background | color   | `#fafafa` | —                                                                        | —       | The page behind everything.                                            | page background                     |
| --color-surface         | color   | `#ffffff` | —                                                                        | —       | Cards, fields, modals.                                                 | cards, fields, modals               |
| --color-page-accent     | surface | `#ededed` | `color-mix(in srgb, var(--color-page-background), var(--color-ink) 6%)`  | —       | Second page color: full-width bands, table headers. Solid or gradient. | full-width bands, table headers     |
| --color-border          | color   | `#d8d8d8` | `color-mix(in srgb, var(--color-page-background), var(--color-ink) 15%)` | —       | Hairlines: card edges, field borders, dividers.                        | card edges, field borders, dividers |
| --color-ink             | color   | `#1a1a1a` | —                                                                        | —       | Body text and headings.                                                | body text, headings                 |

## Brand

| Name                   | Type  | Default   | Derived from                                      | Minimum | Description                                                                                     | Uses                |
| ---------------------- | ----- | --------- | ------------------------------------------------- | ------- | ----------------------------------------------------------------------------------------------- | ------------------- |
| --color-brand          | color | `#5384aa` | —                                                 | —       | Links and focus rings.                                                                          | links, focus rings  |
| --color-primary-action | color | `#295a7e` | `oklch(from var(--color-brand) min(l, 0.45) c h)` | —       | Primary button fill. Defaults to a darkened brand; set this if the button is a different color. | primary button fill |

## Status

| Name            | Type  | Default   | Derived from | Minimum | Description    | Uses          |
| --------------- | ----- | --------- | ------------ | ------- | -------------- | ------------- |
| --color-error   | color | `#b42318` | —            | —       | Error state.   | error state   |
| --color-warning | color | `#b54708` | —            | —       | Warning state. | warning state |
| --color-success | color | `#067647` | —            | —       | Success state. | success state |

## Shell

| Name                | Type    | Default   | Derived from           | Minimum | Description                                                                    | Uses              |
| ------------------- | ------- | --------- | ---------------------- | ------- | ------------------------------------------------------------------------------ | ----------------- |
| --header-background | surface | `#ffffff` | `var(--color-surface)` | —       | Header bar. Defaults to the card surface.                                      | header background |
| --header-ink        | color   | `#1a1a1a` | `var(--color-ink)`     | —       | Header text. Defaults to ink.                                                  | header text       |
| --footer-background | surface | `#1a1a1a` | `var(--color-ink)`     | —       | Footer. Defaults to ink (dark bar). Set both footer tokens for a light footer. | footer background |
| --footer-ink        | color   | `#ffffff` | `var(--color-surface)` | —       | Footer text. Defaults to the card surface.                                     | footer text       |

## Type

| Name                  | Type       | Default                                                    | Derived from | Minimum | Description                                                    | Uses                       |
| --------------------- | ---------- | ---------------------------------------------------------- | ------------ | ------- | -------------------------------------------------------------- | -------------------------- |
| --font-family-heading | fontFamily | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` | —            | —       | h1 through h3 and the hero.                                    | h1-h3, hero                |
| --font-family-body    | fontFamily | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` | —            | —       | Everything else you read, including buttons and fields.        | body copy, buttons, fields |
| --font-family-mono    | fontFamily | `ui-monospace, "SF Mono", Menlo, monospace`                | —            | —       | Code, prices, and badges.                                      | code, prices, badges       |
| --font-size-body      | dimension  | `1rem`                                                     | —            | —       | Size of a paragraph. Headings and small text follow from this. | paragraph text, type scale |

## Geometry

| Name            | Type      | Default  | Derived from | Minimum | Description                                                                  | Uses            |
| --------------- | --------- | -------- | ------------ | ------- | ---------------------------------------------------------------------------- | --------------- |
| --space         | dimension | `1.5rem` | —            | —       | Space between sections. Tighter and looser gaps follow from this.            | section spacing |
| --corner-radius | dimension | `8px`    | —            | —       | Corners on buttons, cards, and fields. Tighter and rounder follow from this. | corner radius   |
| --content-width | dimension | `1290px` | —            | —       | The content column. Narrower measures follow from this.                      | content column  |
