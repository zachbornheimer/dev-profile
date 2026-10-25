# Zysys Admin — lavish default theme

The user named this design system. It replaces the DaisyUI `luxury` fallback from `lavish-axi design`.

## When to use it

Use it for every lavish HTML artifact unless the user named a different look in this turn.

If the artifact mocks a specific app, and that app has its own design system, match that app instead. This system is the default, not an override of a product mock.

Do not load DaisyUI, the Tailwind browser CDN, or `data-theme="luxury"`. Do not invent colors.

## Before writing

Read `README.md` in this directory. For a component you use, read `components/<Name>/preview.html` and reuse its markup and classes. Voice is `guidelines/voice.md`: plain, second person, sentence case, concrete numbers, no marketing language.

If this directory is missing, stop and say so. Do not fall back to DaisyUI.

## Files the artifact must carry

Lavish only serves files that sit next to the HTML. Copy these three into the artifact directory and link them with relative paths. Never prepend `/`.

- `colors_and_type.css` (it imports `tokens.css`, so both files must sit beside the HTML)
- `tokens.css`
- `components.css` (component classes taken from the previews; Cover's canvas `body` rule is omitted)

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="colors_and_type.css">
  <link rel="stylesheet" href="components.css">
</head>
<body>
  <main class="preview">
    <section class="card">
      <h2>Title</h2>
      <p>Body.</p>
      <button class="btn primary" type="button">Save</button>
    </section>
  </main>
</body>
</html>
```

`components.css` already paints `body` with `--color-bg-page`, `--color-text`, and `--font-sans`. One filled `.btn.primary` per view. No decorative icons, emoji, gradients, or shadows beyond `--shadow-segment`. Disabled controls use `--color-accent-disabled`, not opacity.

Use the variables, never the hex: `--color-bg-page`, `--color-surface`, `--color-border`, `--color-text`, `--color-accent`, `--space-*`, `--text-*`, `--font-sans`, `--font-mono`. Page max width is `--layout-max-width` (1180px). Gutter is `--layout-gutter` (24px).

Still follow lavish playbooks for structure (diagram, table, plan, code). Playbooks decide the content. This system decides the paint. Still open the file with `npx -y lavish-axi <html-file>`.
