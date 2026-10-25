---
name: brand-guide-author
description: Use when user says 'create a brand guide', 'expand the brand guide', 'add a section to the brand guide', 'firm up the brand guide', or 'is this brand guide complete?' — authors or expands brand guide HTML.
user-invokable: true
disable-model-invocation: false
argument-hint: "[new <brand>] | [expand <path>] | [audit <path>]"
---

# Brand Guide Author

Produces or expands the canonical brand-guide.html — a single self-contained file that (a) describes the brand decisions, (b) renders every component live using the production runtime CSS so it cannot drift, and (c) the `brand-audit` skill diffs against.

This skill knows:

- The required-core section taxonomy every guide must have
- The conditional sections (include only if the surface uses them)
- The optional product-specific sections (§ deep-dives)
- The can't-drift invariants
- The anti-patterns that produce a guide that looks comprehensive but isn't

## When to use

- **Author mode** — "Create a brand guide for ZBM" / "Write one for AcmeCo": you have brand decisions, you need them codified in a single HTML file that the team treats as canonical.
- **Expand mode** — "Firm up the ZBM brand guide" / "What's missing from the ZAB AI guide?": an existing guide has gaps against the canonical taxonomy; identify them, propose section drafts, write the additions.
- **Audit mode** — "Is this brand guide complete?": diff the existing guide's sections against the canonical taxonomy + judge whether each missing section is required, conditional-applicable, or genuinely N/A for the brand.

Not for:

- Validating a live website against the guide (that's `brand-audit`).
- Writing CSS / runtime code (that's the engagement's own work).
- Pure copy editing or visual design (that's a designer's call, not this skill's).

## Canonical examples

Three working guides exist in this org. Read them when designing a new one:

| Guide      | Path                                                               | Lines | Use as reference for                                                                                                                                                                                                  |
| ---------- | ------------------------------------------------------------------ | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ISA**    | `/tmp/brand-guide-serve/isa.html`                                  | 4983  | **Canonical breadth.** App + dashboard product. Includes every conditional section (wizard, data tables, empty state, alerts, page layouts) plus § deep-dives (anomaly catalog, white-label critique, worked example) |
| **ISJAC**  | `/Users/zbornheimer/Dropbox/Zysys/Software/isjac/brand-guide.html` | 2622  | **Canonical standard.** Nonprofit marketing site. Core sections + Surface taxonomy + voice-per-surface. No app surfaces so no wizard/table/alert sections                                                             |
| **ZAB AI** | `/Users/zbornheimer/Dropbox/Zysys/ZAB AI/brand-guide.html`         | 1769  | **Work-in-progress / parent-org pattern.** Adds Email & transactional, Social & OG, Co-branding sections that ISJAC/ISA don't need. Currently smaller than canonical — used as a "what's missing?" exercise           |

When in doubt, **default to ISA's coverage** and remove what doesn't apply, rather than starting from ZAB AI's smaller surface and trying to add up.

<principles>
  - **The guide is the spec.** Its rendered output IS the expected production behavior, not a screenshot of it. brand-audit reads computed styles from the guide.
  - **The guide cannot lie.** Every color swatch reads from `:root` via `data-css-var`. Every component example uses production CSS, not local one-off styles in the guide.
  - **Sections are content concerns, not page concerns.** "Buttons" exists once, not per-page. Per-page guidance lives in "Web — homepage in use" or a "Page layout templates" section.
  - **Required core is non-negotiable.** Skipping it doesn't make the guide shorter; it makes it incomplete.
  - **Conditional sections are include-if-needed, not include-if-tempted.** A marketing site doesn't need a data-table section.
  - **Voice and tone has per-surface guidance** (hero copy, button verbs, empty states, errors, confirmations) — not a one-paragraph "we are warm and direct" hand-wave.
  - **Every guide has an "If the rule is wrong" meta-rule.** Rules go stale; the guide must say how to amend itself.
</principles>

## Section taxonomy

### Required core — every guide

Every brand guide must have these. Skipping any of them produces an incomplete spec. Order is the recommended reading order.

| #  | Section                             | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| -- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1  | **What's in this guide**            | Table of contents + 1-line per section preview                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2  | **How to read this guide**          | Audience / scope / when-to-override / **if the rule is wrong** meta-rules + "how this document is built"                                                                                                                                                                                                                                                                                                                                                     |
| 3  | **Brand essence**                   | Mission, voice north star, audience, we-are / we-are-not, vocabulary favored / avoided, three sentences that must always be true                                                                                                                                                                                                                                                                                                                             |
| 4  | **Logo & wordmark**                 | Variants, sizes, clearspace, color treatment, identifier alternates, do/don't                                                                                                                                                                                                                                                                                                                                                                                |
| 5  | **Color**                           | Brand-primary / brand-supporting / semantic-status palettes with **dynamic swatches** (data-css-var, read from :root), approved contrast pairs, dark-mode policy, color discipline rules                                                                                                                                                                                                                                                                     |
| 6  | **Page surface & hero treatment**   | Page-canvas gradient, hero overlay or ambient pattern, top-of-hero scrim, optional signature accent, discipline                                                                                                                                                                                                                                                                                                                                              |
| 7  | **Typography**                      | Type families + why this face, scale, rhythm, usage rules, loading, licensing                                                                                                                                                                                                                                                                                                                                                                                |
| 8  | **Spacing & layout**                | Static spacing scale, fluid section padding, container widths, breathing-room rule, vertical rhythm, grid                                                                                                                                                                                                                                                                                                                                                    |
| 9  | **Radius, shadow, motion**          | Radius tokens, shadow tokens, motion duration/easing tokens, reduced-motion behavior                                                                                                                                                                                                                                                                                                                                                                         |
| 10 | **Buttons**                         | Variants on paper, variants on dark, states (hover/focus/active/disabled/loading), anatomy, surface matrix (which variants on which surfaces), CSS reference for primary                                                                                                                                                                                                                                                                                     |
| 11 | **Voice & tone**                    | **Per-surface guidance** — hero copy, button verbs, empty states, errors, confirmations, tone by surface, punctuation & capitalization. NOT a single paragraph.                                                                                                                                                                                                                                                                                              |
| 12 | **Do and don't — the cheat sheet**  | One-page visual reference: stacked do/don't pairs across every concept                                                                                                                                                                                                                                                                                                                                                                                       |
| 13 | **In-use preview**                  | At least one fully-rendered surface (typically the homepage hero) so the reader sees how the rules compose. Uses production CSS — verbatim, not a re-skinned copy.                                                                                                                                                                                                                                                                                           |
| 14 | **Accessibility commitments**       | Contrast targets, keyboard & focus behavior, touch targets, motion preferences, screen readers, dynamic type, color-is-not-the-only-indicator, testing approach                                                                                                                                                                                                                                                                                              |
| 15 | **Token reference**                 | Appendix listing every token by domain (color / surface aliases / typography / spacing / radius / shadow / motion / etc.)                                                                                                                                                                                                                                                                                                                                    |
| 16 | **Implementation notes**            | Pre-commit hooks, CI checks, "when you add a token", "when a token drifts from this document"                                                                                                                                                                                                                                                                                                                                                                |
| 17 | **Drop-in stylesheet for partners** | A single self-contained CSS export that an external partner can paste into a fresh project and get a brand-conformant baseline. Always wrapped in `@layer <brand>` with sub-layers (`tokens → reset → typography → components → utilities`) and namespaced with a brand prefix class so it cannot leak. Includes a Copy-to-clipboard button + per-section ergonomics block (how to use / license / how to override). See "@layer in the drop-in" rule below. |

### Conditional sections — include when the surface uses them

Include only if the brand has the relevant surface. Don't pad guides with sections that don't apply — but don't skip sections the product actually has either.

| Section                          | Include when                                                                                                                                                                                              |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Form fields**                  | The brand has any forms (search, signup, contact, transactional) — include states + validation behavior                                                                                                   |
| **Links**                        | Almost always include — distinguish in-prose links from navigational and external                                                                                                                         |
| **Cards & surfaces taxonomy**    | Surface nesting exists (sections containing panels containing cards) — include the four-pattern decision rule (Section / Panel / Card / Floating) + spec table + worked example + common-mistake callouts |
| **Iconography**                  | Any icon usage — stroke width, sizes, when to use which set                                                                                                                                               |
| **Imagery & photography**        | Any photo or illustration usage — subject matter, what-we-avoid, treatment, rights                                                                                                                        |
| **Multi-step wizard & progress** | App or transactional flow with ≥3 steps                                                                                                                                                                   |
| **Data tables**                  | App / dashboard / admin product                                                                                                                                                                           |
| **Empty state & loading**        | App with state transitions                                                                                                                                                                                |
| **Alerts & toasts**              | App or transactional UI                                                                                                                                                                                   |
| **Page layout templates**        | The brand defines reusable page layouts (e.g., "form page" / "list page" / "detail page" templates)                                                                                                       |
| **Email & transactional**        | The brand sends email — typography fallbacks, HTML-vs-plain-text policy, transactional templates                                                                                                          |
| **Social & OG cards**            | The brand has marketing surfaces — OG image templates with size + type spec                                                                                                                               |
| **Co-branding**                  | The brand is a sub-brand of a parent (ZBM under ZAB AI, etc.) — when each appears, lock-up rules                                                                                                          |
| **Versioning & governance**      | The brand has multiple downstream consumers — bump rules + change-control process                                                                                                                         |

### Optional product-specific deep-dives (§ sections)

Numbered § sections at the end for product-specific complexity that would clutter the canonical sections. Use sparingly. Examples from ISA:

- **§N — Anomaly catalog** — specific UI cases the spec needs to call out by name (e.g., "the Mountain Life MYGA flow has a known D-12 anomaly when the applicant is on a duplicate address")
- **§N — Critique** — a deliberate critique section documenting what the current implementation gets wrong vs the spec, with a remediation path (e.g., "White-label critique & 4-layer overhaul")
- **§N — Worked example** — fully-rendered example of a complex flow with annotations explaining each decision

Don't invent § sections to pad. Use them when there's a real complexity that doesn't fit the canonical taxonomy and the reader needs to understand the WHY.

## The can't-drift invariants

These are what separate a brand-guide HTML from a brand-guide PDF or screenshot deck. **A guide without these is a snapshot, not a spec.**

### 1. Dynamic color swatches

Every color swatch reads its value from `:root` at page load:

```html
<div class="swatch" data-css-var="--isjac-color-brand-deep"></div>
<script>
document.querySelectorAll("[data-css-var]").forEach((el) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(
    el.dataset.cssVar,
  ).trim();
  el.style.background = v;
  // also render hex + oklch labels via the same value
});
</script>
```

**Why:** the guide cannot lie about what color the brand uses. If the token changes in production, the guide updates automatically.

**Anti-pattern:** hardcoded `style="background: #1a2a45"` swatches.

### 2. In-use preview uses production CSS

The "Web — homepage in use" section embeds the actual production component markup with the actual production stylesheet linked. Not a re-skinned copy. Not a screenshot.

**Why:** if the runtime changes a button radius, the preview shows the new radius. If the preview can't render correctly, the runtime is broken — the guide doubles as a regression-detection surface.

### 3. Token reference reads from :root

Same pattern as swatches but for token tables. Each row reads its current value from CSS variables. Don't paste hex values that will drift.

### 4. Component examples use production classes

When showing a button, use the actual `<button class="isjac-btn isjac-btn--primary">`. Not a guide-local `.guide-button-demo` class. The class IS the example.

## `@layer` in the drop-in — when the answer flips

The drop-in stylesheet (§17) is the **only** place a brand guide uses `@layer`. This is deliberate and worth explaining because the rule contradicts the project-level "no `@layer`" guardrail enforced by Stylelint in consumer engagements (see ISJAC's `docs/css-architecture.md`).

The contradiction is real and resolves by who's consuming:

| Consumer                                                                             | Environment                                              | `@layer` is right? | Why                                                                                                                                                                                                                               |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **External partner** (e.g. third-party agency building a fresh e-app from the brand) | Greenfield — no upstream CSS to fight                    | **YES**            | Partner writes their own rules unlayered; spec rule "unlayered beats layered" means their CSS automatically wins over the brand's — no `!important`, no specificity battles, no copying token names. This is the Kelp UI pattern. |
| **Internal engagement** (the brand's own site — ISJAC's runtime + child theme)       | Brownfield — Kadence / WordPress / plugins all unlayered | **NO**             | Brand CSS in `@layer` would LOSE the cascade fight against unlayered upstream rules. The runtime ships unlayered, source-ordered after Kadence.                                                                                   |

**Same brand. Same tokens. Two CSS shapes.** The drop-in stylesheet (§17) is `@layer`-wrapped for partner consumption. The internal production CSS (the runtime in `zysys/wp-runtime` for ISJAC, or the equivalent for ZBM/ZAB AI when they have one) ships unlayered. When the internal team needs to vendor a copy of the §17 drop-in for their own use, they manually strip the `@layer <brand> { ... }` wrap. A `sed -i '/^@layer/d; /^}$/d'` script handles the mechanical case; a more careful pass is needed when the drop-in has internal sub-layer structure.

What this means for the author:

- The §17 drop-in always uses `@layer <brand>` with sub-layers. No exceptions.
- The §17 section copy explicitly tells partners "you write plain unlayered CSS; we lose gracefully."
- The §17 section also tells the internal team "if you vendor this for the brand's own site, strip the wrap first — see [project's css-architecture.md] for why."
- Stylelint in the consumer engagement still bans `@layer` in authored CSS. That rule applies to the engagement's CSS files, not to the brand-guide HTML itself.

## Anti-patterns

These produce guides that look comprehensive but aren't. Avoid each.

### Hardcoded swatches

```html
<!-- BAD: swatch frozen at write-time, drifts from production -->
<div style="background: #1a2a45"></div>

<!-- GOOD: swatch reads live -->
<div data-css-var="--isjac-color-brand-deep"></div>
```

### Voice & tone as one paragraph

```markdown
<!-- BAD -->

## Voice & tone

We are warm, direct, and considered.

<!-- GOOD -->

## Voice & tone

### Hero copy

One sentence. Verb-led. No comma overload.

### Button verbs

"Become a member" not "Sign up". "Donate" not "Give a gift".

### Empty states

Acknowledge the empty, tell the user what to do next.

### Errors

Plain language. Tell the user what went wrong AND how to recover.

### Confirmations

Past tense. Short. No exclamation marks.

### Tone by surface

Marketing hero: warm. App dashboard: precise. Transactional email: terse.
```

### Token reference that's a stale copy

If the token table is hand-maintained and not reading from :root, it will drift the moment someone updates the runtime without remembering to update the guide. Make the table live.

### Missing "if the rule is wrong" meta-rule

Without this, the guide is a totem; with it, the guide is a living document. The meta-rule should say:

- This document is opinionated and will be wrong sometimes.
- Disagree by opening a PR against this file, not by overriding in component code.
- The cheat sheet (§Do and don't) is the conflict-resolution priority — when sections appear to disagree, the cheat sheet wins.

### Inventing § sections to pad

§ sections should exist because there's real product-specific complexity. Don't add § sections to make the guide look longer. ZAB AI doesn't need an "anomaly catalog" because it's a brand, not a product with edge cases. ISA does because it's a complex app.

### Skipping in-use preview

Without a fully-rendered surface using production CSS, the guide is theory. The preview is what makes the guide accountable to reality.

## Authoring workflow

### New guide (from scratch)

1. **Pick a base.** Start from ISJAC if marketing site, from ISA if app/dashboard, from ZAB AI if parent-org with co-brand concerns.
2. **Adjust brand-prefix.** Change every `--isjac-*` to `--{brand}-*`, every `.isjac-*` class to `.{brand}-*`.
3. **Strip sections you don't need.** Marketing site? Drop wizard/tables/alerts. Don't keep empty stubs.
4. **Write Brand essence first.** Mission, voice north star, we-are/we-are-not, vocabulary. If this doesn't land, the rest of the guide has nothing to anchor to.
5. **Write Color second.** Decide the 6-ish brand colors + semantic-status palette. Wire the dynamic swatches.
6. **Then typography, spacing, radius/shadow/motion.** The foundations every component will reference.
7. **Then components.** Buttons first, then form fields, then links, then conditional component sections.
8. **Then voice & tone with per-surface guidance.** This is the section that always gets shortchanged.
9. **Then do/don't cheat sheet, accessibility, token reference, implementation notes.**
10. **Then the in-use preview.** Render the actual homepage hero using production CSS.

### Expanding an existing guide

1. **Diff against required-core.** List every required section the guide lacks.
2. **Diff against conditional sections.** For each conditional section the guide lacks, judge whether the surface uses it. Don't pad.
3. **Audit the can't-drift invariants.** Are swatches dynamic? Token reference live? In-use preview using production CSS?
4. **Audit Voice & tone for per-surface depth.** A single paragraph fails; a section with hero/button/empty/error/confirm/tone-by-surface subsections passes.
5. **Audit § deep-dives.** Are any genuinely product-specific? Or were they invented to pad?
6. **Propose section drafts BEFORE writing them.** Show the user the outline + 2-3 paragraphs of why-it-matters per missing section. They approve before you write 200+ lines of HTML.

### Audit-only mode

Run the diff above but produce only the gap list + recommendation. No HTML writing. Useful for "is this guide complete?" questions.

## Output expectations

- New guides are single self-contained .html files at the project root (alongside `brand-guide.html` if that's the convention, or named explicitly when there are multiples).
- Expansions are edits-in-place; preserve the existing structure and write the new sections in the canonical position.
- Audits are markdown briefs with: (a) what's there, (b) what's missing required, (c) what's missing conditional (with judgment about whether applicable), (d) can't-drift violations, (e) prioritized recommendation list.

## What this skill does NOT do

- Doesn't choose brand colors / typefaces / voice — that's the human's design work. The skill structures the writing of decisions, not the decisions themselves.
- Doesn't write the production CSS — the guide REFERENCES it; it lives in the engagement repo.
- Doesn't deploy or version the guide — that's the project's own deploy story.
- Doesn't lint the guide for HTML correctness — use the project's existing HTML linter.

## Pairs with

- **brand-audit** — validates live URLs against the guide this skill produces. Authoring + auditing are two halves of the same loop.
- **spec-writer** — for general software specs (not brand-specific). Use spec-writer when the artifact is an API or system spec, not a brand reference.
