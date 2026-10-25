---
name: html-output
description: Use when producing a plan, review, report, explainer, spec, or dashboard longer than ~100 lines, or any artifact you'll want to read, share, or tune. Prefer HTML over Markdown for these. Always end an interactive artifact with a copy-as-JSON or copy-as-prompt button.
---

# HTML Output

Markdown has a 100-line readability ceiling. Beyond that — for plans, reviews,
reports, explainers, specs, dashboards, and throwaway editors — HTML produces
work people actually read and share. Use it by default for anything non-trivial.

## When to reach for HTML

| Situation                     | Why HTML wins                                                                    |
| ----------------------------- | -------------------------------------------------------------------------------- |
| Plan or spec > ~100 lines     | Tabs, nav links, and visual hierarchy make it scannable; Markdown becomes a wall |
| Review or report to share     | An HTML file opens anywhere; Markdown requires a renderer                        |
| Design exploration            | CSS + SVG express design intent; ASCII diagrams in Markdown don't                |
| Code explanation / PR writeup | Rendered diffs, inline margin annotations, color-coded findings by severity      |
| Throwaway editor / tuning UI  | Sliders, knobs, drag-and-drop — then a copy-out button to reuse the result       |
| Any artifact with a diagram   | SVG diagrams > ASCII; no contest                                                 |

Markdown is still fine for short notes, commit messages, and content that IS
going into a Markdown-native system (READMEs, GitHub PR bodies, etc.).

## Always include a copy-out button on interactive artifacts

Every throwaway editor or interactive artifact ends with a **"Copy as JSON"** or
**"Copy as prompt"** button that serializes the current state back to something
pasteable into Claude Code or committable to a file. The loop must close.

Without this, the artifact is a dead end. With it, it's a tight loop.

## Example prompts (use these verbatim or adapt)

**Design exploration — multiple options side-by-side:**

> _I'm not sure what direction to take the onboarding screen. Generate 6 distinctly
> different approaches—vary layout, tone, and density—and lay them out as a single
> HTML file in a grid so I can compare them side by side. Label each with the
> tradeoff it's making._

**Implementation plan with mockups and code snippets:**

> _Create a thorough implementation plan in an HTML file. Include mockups, data
> flow diagrams in SVG, and the key code snippets worth reviewing. Make it easy
> to read in one sitting._

**Code / PR explainer:**

> _Help me review this PR by creating an HTML artifact. I'm not familiar with the
> streaming/backpressure logic — focus on that. Render the actual diff with inline
> margin annotations, color-code findings by severity._

**Technical explainer with diagram:**

> _I don't understand how our rate limiter works. Read the relevant code and produce
> a single HTML explainer: a diagram of the token-bucket flow, the 3–4 key code
> snippets annotated, and a "gotchas" section at the bottom. Optimize it for
> someone reading it once._

**Throwaway editor for structured data:**

> _I need to reprioritize these 30 Linear tickets. Make an HTML file with each
> ticket as a draggable card across Now / Next / Later / Cut columns. Pre-sort by
> your best guess. Add a "copy as Markdown" button that exports the final ordering
> with a one-line rationale per bucket._

**Prompt / template tuner:**

> _I'm tuning this system prompt. Make a side-by-side editor: editable prompt on
> the left with variable slots highlighted, three sample inputs on the right that
> re-render the filled template live. Add a character/token counter and a copy
> button._

## What HTML can express that Markdown cannot

- Tables with real CSS (sortable, filterable, color-coded)
- SVG diagrams and flowcharts
- Animations and interactions (sliders, toggles, drag-and-drop)
- Tabs and collapsible sections for long structured content
- Rendered diffs with syntax highlighting and margin annotations
- Spatial layouts with absolute positions and canvas elements
- Mobile-responsive reading experiences

## How to prompt for HTML (it's simple)

Add _"make an HTML file"_ or _"make an HTML artifact"_ to any request. Claude will
handle the rest. The main thing is knowing what you want the artifact to DO and how
you'll USE it — that context shapes the structure more than any template.

## Gotchas

- **Token cost is higher, but worth it.** A 1M-context window makes this
  negligible in practice. A plan that gets read is worth 3× the tokens of one
  that doesn't.
- **HTML files are shareable via upload link; Markdown is not.** When the
  artifact needs to reach a colleague, HTML wins on distribution alone.
- **Don't use HTML for content that IS going into Markdown-native systems.**
  GitHub PR bodies, commit messages, and READMEs are Markdown contexts — keep them
  as Markdown.
- **The copy-out button is not optional on interactive artifacts.** If the user
  tunes something in a slider-based editor, they need a way to get that result
  back. Always close the loop.
- **Use Claude Code's full context for rich artifacts.** Claude Code can read
  your filesystem, MCPs (Slack, Linear), browser (Chrome MCP), and git history
  before generating. For a review or report, that context is the whole point.
