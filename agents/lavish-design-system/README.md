# Zysys wp-admin design system

## Product context
Zysys plugins live inside wp-admin. Screens must feel native to WordPress and be quieter than WP core: data-dense but calm, white cards on the `--color-bg-page` canvas, one blue accent, no decoration. Source screens: `guidelines/approved-screens/SEO.html` and `SitePerformance.html`.

## Tokens (`colors_and_type.css`)
The values are in `tokens.json`; `tokens.css` is generated from it and `colors_and_type.css` imports it, so linking `colors_and_type.css` still works.
Always use the variable, never the hex.
- Surfaces: `--color-bg-page`, `--color-surface`, `--color-surface-subtle` (row hover, bar tracks), `--color-divider`, `--color-row-divider`
- Borders: `--color-border`, `--color-border-control`, `--color-border-input`, `--color-border-danger`
- Text: `--color-text`, `-secondary`, `-muted`, `-subtle`, `-faint`, `--color-on-accent`
- Accent: `--color-accent`, `-hover`, `-bg` (hover/selected fill), `-disabled`
- Status: `--color-success[-text|-bg]`, `--color-warning[-text|-bg|-border]`, `--color-error[-text|-bg|-border|-soft]`
- Search preview: `--color-serp-title`, `--color-serp-desc`
- Type: `--font-sans`, `--font-mono`; sizes `--text-page-title` 23, `--text-section-title` 15, `--text-body` 13, `--text-meta` 12, `--text-badge` 11 (uppercase), `--text-mono` 12.5; weights 400/500/600
- Space `--space-2..28`; radii `--radius-card` 6, `--radius-control` 4, `--radius-badge` 3, `--radius-pill` 999; shadow `--shadow-segment`; layout `--layout-max-width` 1180px, `--layout-card-min` 320px

## Layout idiom
- Shell: max-width 1180px, 24px gutter, 20px vertical gap.
- Page header: 23px/500 title, 13px muted meta line, status pill on the right. Tabs sit under it with a 2px accent underline.
- Card grid: `repeat(auto-fit, minmax(320px, 1fr))`, 16px gap. Card: white, 1px border, 6px radius, 20px padding.
- List card: header bar (title + 12px sub, divider below), grid rows (9px 20px padding), `overflow-x:auto` wrapper with a `min-width` inner (720px / 680px), "Show all" link-button footer.
- Segmented filter: grey track, white active item with `--shadow-segment`, muted counts.
- Numbers use tabular nums. Routes use mono.

## Voice
See `guidelines/voice.md`. Plain, second person, concrete numbers, says what happens and what is stored. "A healthy request writes nothing." Sentence case. Meta lines use "·" separators.

## State semantics
- Green dot = on / healthy
- Amber = over budget (p95 above the budget tick)
- Red = 3x budget or more
- Grey dot = off
- Destructive actions use `--color-error-text` outlines; the confirm button stays `--color-error-soft` until the user types DELETE.

## Do
- Link `colors_and_type.css` and use variables only.
- Say what a control does and what gets stored.
- Keep one primary filled button per view.
- Show the empty/healthy state in words ("No remote call is failing repeatedly.").

## Don't
- Invent colors, gradients, or shadows beyond `--shadow-segment`.
- Use icons or emoji as decoration.
- Use title case, exclamation marks, or marketing language.
- Dim disabled buttons with opacity; use `--color-accent-disabled`.
- Load the dc runtime (`support.js`) or React in cards.
