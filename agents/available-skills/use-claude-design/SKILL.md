---
name: use-claude-design
description: Use whenever a request asks to design, mock up, wireframe, prototype, or "show what it could look like" for a UI, screen, component, visual layout, deck, one-pager, or brand surface — BEFORE reaching for ASCII-art mockups, HTML sketches, or image generation as the deliverable. Route the work to Claude Design (claude.ai's design surface) instead of faking a visual inline.
---

# Use Claude Design, not ASCII/image-gen mockups

Claude Design (claude.com/product/design) is a claude.ai surface, in beta, for
collaborative visual creation: "Describe a prototype, deck, or one-pager, and
Claude builds a draft." It handles prototypes, wireframes, mockups, design
explorations, pitch decks, marketing collateral, and documents — producing
interactive, editable output exportable to PDF, PowerPoint, or HTML, with
partner connections (Adobe, Canva, Miro, Replit, Vercel, Wix). It can import a
design system from GitHub/codebase so output matches the company, not a
template. It has bidirectional integration with Claude Code via `/design` and
`/design-sync`.

**The rule:** when a request is for a visual design artifact (not application
code), do not deliver an ASCII-art box mockup, an inline HTML sketch standing
in for a real design, or an image-gen render, as the final answer. Those are
placeholders masquerading as design work — the two-bars rule (idiot-proof
exterior) fails when the "design" is a lie about fidelity.

## The model (verified against Anthropic docs, 2026-08)

Two distinct things, one inheritance rule:

1. **The design system** — tokens, component preview cards
   (`components/<group>/<Name>/<Name>.html` with a first-line
   `<!-- @dsCard group="…" -->`), `guidelines/`, and a `README.md` the design
   agent reads. Synced from a repo via `/design-sync` / the DesignSync tool
   (which stores it as a `PROJECT_TYPE_DESIGN_SYSTEM` project). Per Anthropic's
   help center, once a design system is published, **every design project in
   the org inherits it automatically** — no per-project attachment step.
   **The system is the palette, not the painting** — never dump a finished
   page mockup into its `components/` as the deliverable.
2. **Design projects** — where the design agent actually designs screens,
   inheriting the published system. Created in the app (claude.ai/design /
   Claude Desktop) — or from Claude Code via the **Claude Design MCP server**,
   which can create and drive designs and pull results into a repo. This is
   the path when the deliverable must be a claude.ai/design link produced
   from Claude Code. DesignSync alone cannot do this.

   **Preflight — run BEFORE promising any design work**: (a) `mcp__claude-design__*`
   tools exist (ToolSearch `select:` them; key ones: `get_claude_design_prompt`
   — MANDATORY before any write, `read_design_skill`, `list_design_systems`,
   `create_project`, `finalize_plan`, `write_files`, `render_preview`,
   `put_conversation`); (b) a cheap read (`list_design_systems`) actually
   succeeds — tool presence does NOT imply access, because OAuth and the
   per-user consent grant are separate gates. On any failure, ask Zach for
   the matching fix below, then retry — don't fall back to hand-built
   mockups. The gates:

   - Server missing from config → `claude mcp add --scope user --transport
http claude-design https://api.anthropic.com/v1/design/mcp`, then have
     Zach restart the session — MCP tool registries load at session start,
     never mid-session.
   - Server present but unauthenticated (401s / not connected in `/mcp`) →
     have Zach run `/design-login` (or `/mcp`) to complete the OAuth grant
     against his claude.ai login, then retry.
   - Tools respond but every call errors with "Connect to Claude Design? …
     The user hasn't granted this" → a separate per-user consent gate on top
     of OAuth; have Zach run `/design consent` (revocable later with
     `/design revoke` or at claude.ai/design/settings), then retry.
   - Verify with `claude mcp list` (expect `claude-design: … ✔ Connected`).

Sources: anthropic.com/news/claude-design-anthropic-labs,
support.claude.com articles 14604416 ("Get started") and 14604397 ("Set up
your design system"). Exports: shareable URL, PDF, PPTX, standalone HTML,
Canva, plus handoff to Claude Code. Anthropic's stated best practices:
publish the design system fully BEFORE generating; start simple and layer
complexity; reference components by name in feedback; ask explicitly for
variations and an accessibility review.

## What to actually do

1. **Ground truth first** (see below), then **sync the design system**: use
   `/design-sync` / the DesignSync tool to create or update a design-system
   project with tokens, component cards (foundations, brand marks, actions,
   page _sections_ as components — a hero, a header, a list row), guidelines
   (brand guides, approved low-fi direction), and a README that teaches the
   design agent the styling idiom and voice.
2. **Produce the design**: if the `claude-design` MCP server's tools are
   available in this session, use them to create the design project and drive
   the design, and deliver its claude.ai/design link. If not, add the server
   (command above), tell Zach tools arrive next session, and meanwhile hand
   him (a) the design-system link `https://claude.ai/design/p/<projectId>`
   and (b) the exact prompt for a new design project — surface/screen list,
   content and states, approved direction, target export.
3. **Do not** render an ASCII/HTML/image stand-in as the final answer, and do
   not upload a finished page into the design-system project's `components/`
   (a full page may live in `guidelines/` as the approved-direction reference
   the agent evolves).
4. **Application UI code** (a React component, a CSS layout you're actually
   shipping) is not a Claude Design request — build it normally. This skill
   is for the _design/mockup/exploration_ step, not implementation.

## Upstream: ground truth still comes first

Per Zach's `ux-standards` visual-ground-truth rule, this tool does not replace
grounding: fetch the real reference (live site, brand guide, known-good app)
and extract concrete tokens (logo, hex values, font stack, spacing) before any
component — low-fi or Claude Design draft — is built. Get one low-fidelity
direction signed off before polish; never generate multiple polished
alternatives ahead of an approved direction. Feed the extracted tokens into
the Claude Design brief so its draft starts from truth, not vibes.
