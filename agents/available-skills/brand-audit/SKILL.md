---
name: brand-audit
description: Use when user says '/brand-audit <url>', 'audit the homepage', 'check brand conformance', 'brand-conform', or 'does this match the brand guide' — audits live URL against brand guide HTML.
user-invokable: true
disable-model-invocation: false
argument-hint: "<url> [--page-only | --css-only | --propose-fixes]"
---

# Brand Audit

Dissolves the "does this look on-brand?" question into a per-axis diff between a live page and the project's brand guide. Vision and human eyes both miss small typography drift (Inter rendering where IBM Plex Mono is spec'd reads as "small uppercase blue text" to both). This skill replaces visual judgment with `getComputedStyle` probes.

<principles>
  - The brand guide is the spec. Its rendered computed styles ARE the expected values. Do not re-derive expected values from prose.
  - Drift lives in CSS class rules. Audit the system, not the page rendering.
  - Fixes go in the token layer. Wrong-token drift is fixed by changing which token a component references — never by hardcoding a value in component CSS.
  - On-dark variants use surface-aware context tokens. Never per-component `--*-color-on-dark` overrides in component rules.
  - Trust the computed style. Vision LLMs and human eyes both miss typography axes.
</principles>

## Prerequisites

Stop and tell the user what's missing if any of these fail.

### 1. A local brand guide

Look in this order:

1. `brand_guide` path in `./.brand-audit/config.yaml`
2. `./brand-guide.html` at the project root
3. Any `brand-guide.html` referenced by `package.json`, `composer.json`, or a `Makefile`

If none found:

> No brand guide found at `./brand-guide.html` or `./.brand-audit/config.yaml`. The audit needs a canonical brand guide to compare against. Create one (try `spec-writer` for a template), then point me at it via `./.brand-audit/config.yaml`:
>
> ```yaml
> brand_guide: ./path/to/brand-guide.html
> brand_guide_url: http://127.0.0.1:8770/brand-guide/
> brand_prefix: isjac
> ```

### 2. The brand guide must be HTTP-served

Computed-style probing requires the guide to render in a real browser. Verify the configured URL responds. If not, tell the user how to serve it (`python3 -m http.server`, `npx serve`, or the project's own dashboard).

### 3. Chrome MCP tools available

The probe uses `mcp__claude-in-chrome__javascript_tool`. Load via ToolSearch first if not present. Fall back to Playwright-via-Bash and warn that audit speed drops substantially.

## The audit loop

Each step's output is the next step's input. Do not skip; the structure is the contract.

### Step 1 — Classify what's on the page

Dispatch a fresh `general-purpose` Agent to inventory the target URL. The classifier should reason about each visible element before assigning a category, not pattern-match from a screenshot.

<example>
<agent-prompt>
You're auditing http://localhost:10033/ against the ISJAC brand vocabulary. For each visible component instance, return:

- the brand category it fits from the list below
- the selector or DOM path to reach it
- a one-line text sample (if textual)

Categories: page_surface, section_default, section_dark, hero_panel, card, hero_h1, hero_subhead, section_h2, section_h3, body_paragraph, eyebrow, button_primary, button_on_dark_primary, input_text, prose_link, footer_link, site_header, site_footer, icon_inline, ...

For each element, first think in `<thinking>` tags about what role this element actually plays on the page (does it function as a hero h1? a card? an eyebrow?), THEN assign the category. If nothing fits cleanly, return "unclassified" with a short description.

Return as a flat list. ~50–100 entries expected for a typical homepage.
</agent-prompt>

<expected-output-shape>
- [#12] hero_h1 — selector: `.entry-content .alignfull.is-style-isjac-hero h1` — text: "Welcome back, Zachary."
- [#21] eyebrow  — selector: `p.isjac-eyebrow` (1st of 2) — text: "Hall of Fame"
- [#34] button_on_dark_primary — selector: `.isjac-hero .isjac-btn--primary` — text: "Dashboard"
- [#U1] unclassified — selector: `#wpadminbar` — what: WP admin bar (out of scope)
</expected-output-shape>
</example>

The classifier's structure (one entry per instance, with selector) is what Step 2 consumes. Do not skip this step and enumerate from your own visual reading — fresh agent + structured vocabulary catches what a context-loaded operator misses.

### Step 2 — Probe both surfaces

For each classified instance, read computed styles via Chrome MCP. Probe these axes per component type:

| Bundle      | Properties                                                                                            |
| ----------- | ----------------------------------------------------------------------------------------------------- |
| typography  | `font-family`, `font-size`, `font-weight`, `line-height`, `letter-spacing`, `text-transform`, `color` |
| surface     | `background-color`, `background-image`                                                                |
| shape       | `border-radius`, `border-width`, `border-color`                                                       |
| space       | `padding`, `margin`, `gap`                                                                            |
| pseudo      | `::before` / `::after` `{ content, background-image, inset }`, `::placeholder { color }`              |
| interactive | trigger `:hover` / `:focus-visible` via Chrome MCP `hover`, re-read, compare to rest                  |
| icon        | SVG bbox, `stroke-width`, `fill`                                                                      |

Run the same probe on the brand guide. The brand guide's computed style IS the expected value. Diff per-axis.

### Step 3 — Verify the brand class is applied

For each classified element, check `el.classList` contains the project's brand-prefixed class (e.g. `isjac-eyebrow` when prefix is `isjac`). Report:

- elements with no brand class at all (markup gap)
- elements where the brand class lives on an ancestor instead of the element itself (call out; convention varies)

### Step 4 — Verify the class definition uses tokens

Grep the project's CSS for each component class that fires on the live page. Catch two distinct drift classes:

- **Hardcoded value** — `font-size: 14px` instead of `var(--isjac-font-size-*)`
- **Wrong token** — token referenced but the wrong one chosen (the common case)

<example>
  <finding>Body paragraph renders at 16px but spec says 17px.</finding>
  <thinking>
    The site uses `--isjac-font-size-base` (16) for body text where the spec calls for `--isjac-font-size-body` (17). Stylelint would accept this — both are valid tokens — but the role-token mapping is wrong. Body is supposed to consume the body slot, not the base slot.
  </thinking>
  <diagnosis>
    Wrong-token drift. Both files token-discipline correctly; the developer chose the wrong primitive from the type ramp.
  </diagnosis>
  <fix-direction>
    Swap the token reference in the body p rule: `var(--isjac-font-size-base)` → `var(--isjac-font-size-body)`. Better: add `--isjac-body-font-size: var(--isjac-font-size-body)` to the semantic token layer and reference that, so future body sizing changes happen once.
  </fix-direction>
</example>

### Step 5 — Confirm cascade

For each drifted property, walk `document.styleSheets` to find the winning rule. Report the winning selector + file:line, plus whether the rule is in the project's theme (fixable by token swap) or upstream (Kadence parent / Gutenberg / plugin — requires specificity work).

If a fix's intended rule will be beaten upstream, surface that before proposing the fix. A "fix" that won't land is worse than no fix.

### Step 6 — Propose fixes

Triggered by `--propose-fixes` or when the user requests fixes.

<thinking>
  Before naming a fix, classify which architecture rule applies. Most drifts fall into one of three buckets: (a) a primitive token is missing entirely, (b) the right token exists but a component references the wrong one, (c) the right token + reference both exist but cascade is beaten upstream. The bucket determines the file you edit.
</thinking>

<architecture-rules>
The rules below shape every fix. They exist because the alternative — patching values in component CSS — produces a drift treadmill where the same bug recurs in different components.

1. Token swaps go in `tokens.css`, not in component CSS. Reason: component CSS is touched by many features; tokens.css is touched only when the brand changes. Putting the fix in component CSS spreads the spec across N files.

2. Missing primitives go in `tokens.css` `:root` first, then the semantic token references the new primitive, then the component CSS references the semantic token. Three edits, three files, in that order. Reason: every value the brand uses needs a name before any component can consume it.

3. On-dark variants are surface-aware context tokens, not per-component overrides:

   ```css
   :root {
     --x-eyebrow-color: var(--x-color-brand-mid);
     --x-eyebrow-color-on-dark: var(--x-color-paper);
   }
   :is(.x-band--invert, .x-footer, .x-is-style-hero) {
     --x-eyebrow-color: var(--x-eyebrow-color-on-dark);
   }
   .x-eyebrow {
     color: var(--x-eyebrow-color);
   }
   ```

   Component CSS reads only `--x-eyebrow-color`. The cascade decides which value resolves. Reason: per-component on-dark overrides multiply by N components × M dark surfaces; surface-aware tokens scale at 1 token per axis.

4. Hover transforms are off unless the brand guide demonstrates them. Spec usually reserves `transform: translateY(1px)` for `:active` (press-down), with `:hover` being color/border only. Reason: lifts read as "this is a card you can pick up" — wrong affordance for a button.

5. `<input>` needs `color`, `-webkit-text-fill-color`, and `caret-color` set together. WebKit overrides `color` with `-webkit-text-fill-color` in some contexts (system theme, autofill). Setting only `color` leaves typed text invisible on dark surfaces. Reason: this isn't a token-system issue; it's a UA quirk that needs explicit handling at the input level.
   </architecture-rules>

For each drift, the proposed fix names: the file:line to edit, the existing value or token reference, the new value or token reference, and (if a new primitive or semantic token is needed) the additions to `tokens.css`.

### Step 7 — Re-probe and verify

Re-run Step 2's probe on the affected instances after each fix lands. Every fixed drift must close to zero before declaring complete. A "fix" that doesn't close the diff is a bug — investigate the typical causes: more-specific upstream rule, autofill override, wrong selector in the fix, or a token that resolves to a different value than the developer expected.

## Output format

<example>
```markdown
# Brand audit — http://localhost:10033/

**Spec:** <http://127.0.0.1:8770/brand-guide/>
**Audited:** 2026-05-17T14:32:01Z

## Summary

- 53 classified component instances
- 12 drifted axes across 5 components
- 1 unclassified element (WP admin bar — out of scope)
- 0 cascade conflicts

## Per-component drift

### eyebrow (2 instances)

Spec selector: `.eyebrow` in brand-guide

| Axis           | Expected      | Actual | Winning rule                          |
| -------------- | ------------- | ------ | ------------------------------------- |
| font-family    | IBM Plex Mono | Inter  | `.isjac-eyebrow` in 40-homepage.css:1 |
| font-size      | 11px          | 14px   | same                                  |
| font-weight    | 400           | 500    | same                                  |
| letter-spacing | 0.22em        | 0.08em | same                                  |

**Fix:**

1. Add primitive to plugin/tokens.css `:root`:

   ```css
   --isjac-font-size-eyebrow: 0.6875rem;
   --isjac-letter-spacing-eyebrow: 0.22em;
   ```

2. Add semantic tokens to plugin/tokens.css `:root`:

   ```css
   --isjac-eyebrow-font-family: var(--isjac-font-mono);
   --isjac-eyebrow-font-size: var(--isjac-font-size-eyebrow);
   --isjac-eyebrow-font-weight: var(--isjac-font-weight-regular);
   --isjac-eyebrow-letter-spacing: var(--isjac-letter-spacing-eyebrow);
   --isjac-eyebrow-color: var(--isjac-color-brand-mid);
   ```

3. Rewrite `.entry-content .isjac-eyebrow` in 40-homepage.css to consume the semantic tokens.

```text
</example>

## Component vocabulary

The default ~30-component vocabulary lives in `~/.agents/available-skills/brand-audit/template-components.yaml`. Projects override by dropping a customized copy at `./.brand-audit/components.yaml`.

## Drift patterns the eye misses

Probe for these explicitly — they share one property: the surface-level signal reads as conformant while one or more underlying axes are wrong.

<example>
<pattern>Eyebrow renders as Inter / medium / under-tracked instead of mono / regular / 0.22em.</pattern>
<thinking>
"Small uppercase brand-mid text" pattern-matches as "eyebrow" to vision, but font-family and tracking are wrong. The shape signals the role; the axes that define the brand fail underneath.
</thinking>
<probe>font-family, font-weight, letter-spacing — all three must match the brand-guide eyebrow's computed style.</probe>
</example>

<example>
<pattern>Button background and text colors are swapped on dark surfaces.</pattern>
<thinking>
A primary CTA on a hero with paper text and brand-deep background is the inverse of what `btn-on-dark-primary` specs (paper background, brand-deep text). The button still reads as "primary CTA" because both color pairs are brand colors. Pre-spec themes often defended the inversion in comments.
</thinking>
<probe>color + background-color on `.btn-on-dark-primary` consumers must match the brand-guide values exactly, not just be drawn from the brand palette.</probe>
</example>

<example>
<pattern>Overlay gradient renders fully opaque, hiding the background image.</pattern>
<thinking>
`color-mix(in srgb, var(--ink) 70%, var(--ink))` mixes ink with itself — produces 100% opaque ink. The intended `color-mix(... , transparent)` form keeps alpha at 70% so the photo shows through. Both are valid CSS; the difference is the second argument.
</thinking>
<probe>Read the resolved `background-image` of the `::before` overlay; if the gradient's stops don't include alpha < 1, the image won't show through even when present.</probe>
</example>

## Failure modes

| Symptom | Action |
|---|---|
| No brand guide found | Stop; instruct user to create one |
| Brand guide unreachable via HTTP | Stop; instruct user how to serve it |
| Chrome MCP unavailable | Stop; explain audit requires a real browser |
| Target URL returns 404 | Stop; report network error |
| Brand guide declares a component in CSS but doesn't demo it | Surface as structural gap in the guide; no expected value to diff against |
| Cascade winner is upstream and unreachable | Report; propose specificity override OR removing upstream interference |
| Vision classifier disagrees with computed-style fingerprint | Trust the computed-style fingerprint |

## Worked example — one drift, end to end

<example>
<step-1>
Agent classifies a `<p class="isjac-eyebrow">Hall of Fame</p>` as `eyebrow`.
</step-1>

<step-2>
Probe both surfaces:
- guide `.eyebrow` → IBM Plex Mono / 11px / 400 / 0.22em / brand-mid
- live  `.isjac-eyebrow` → Inter / 14px / 500 / 0.08em / brand-mid

Diff: 4 axis mismatches (font-family, font-size, font-weight, letter-spacing).
</step-2>

<step-3>Brand class `isjac-eyebrow` present on the element ✓</step-3>

<step-4>
Grep `40-homepage.css` for `.isjac-eyebrow`:
- references `var(--isjac-font-size-small)` for font-size → wrong primitive (small=14, spec wants 11)
- hardcodes `letter-spacing: 0.08em` → no token exists for 0.22em
- doesn't set font-family at all → inherits Inter from body, spec wants Plex Mono
</step-4>

<step-5>
Walk styleSheets: `.entry-content .isjac-eyebrow` in 40-homepage.css wins for every property. No upstream interference.
</step-5>

<step-6>
Bucket: missing primitive (eyebrow size, letter-spacing) + missing semantic-token slot + wrong primitive reference. Three edits.

Fix:
1. plugin/tokens.css `:root` — add primitives `--isjac-font-size-eyebrow: 0.6875rem`, `--isjac-letter-spacing-eyebrow: 0.22em`
2. plugin/tokens.css `:root` — add semantic slots `--isjac-eyebrow-{font-family,font-size,font-weight,letter-spacing,color}`, each referencing the right primitives
3. 40-homepage.css `.entry-content .isjac-eyebrow` — replace direct primitive refs with the semantic slots
</step-6>

<step-7>
Re-probe: live `.isjac-eyebrow` now computes IBM Plex Mono / 11px / 400 / 2.42px (=0.22em on 11) / brand-mid. Diff closes to zero. Done.
</step-7>
</example>
```
