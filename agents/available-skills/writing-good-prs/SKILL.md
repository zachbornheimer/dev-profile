---
name: writing-good-prs
description: >-
  Write pull request bodies a reviewer can act on: motivation first, what and
  why per change grounded in the real diff, testing with named commands, and
  reviewer notes for risky spots. Use when opening or rewriting a PR
  description, when a PR body lacks context or testing detail, or when a
  handoff says to load writing-good-prs. Ends with a paste-ready template.
  Before drafting, read the target repository's contributing guide and follow
  it. Their submission path and required sections win. Never disclose an agent.
---

# writing-good-prs — bodies a reviewer can act on

The diff tells a reviewer what the code does. The body tells them why the
change exists, how it was proven, and where to look first. A reviewer who
opens the PR cold must never have to reconstruct any of that from the diff.

Canonical path (paste this into prompts and handoffs):

```text
~/.agents/available-skills/writing-good-prs/SKILL.md
```

## Target repository first

Before drafting a body, read the target repository's contributing guide, pull
request template, and title rules. Do this before `gh pr create`.

Their path wins. If they do not accept external pull requests, or GitHub will
not let this account open one, stop and use the path they name (an issue or a
discussion). Do not open a pull request and do not treat the refusal as a
content rejection.

Their required sections, title format, sign-off, and test commands win over
the template below. Use the template only to fill gaps their guide does not
cover. Never add an agent, tool, model, or session disclosure, even when their
guide asks for one. The writing reads as the user's.

## Rules

1. **Motivation first.** Open with the problem, not the fix: what was broken,
   slow, or missing before this change, with the context a maintainer who does
   not know your fork, your ticket history, or your local setup needs. Never
   open with implementation detail, and never make the reader open a link to
   learn why the change exists.
2. **What and why, per change.** Name real files and symbols from the actual
   diff, not areas or vibes. State the primary change in the first sentence of
   the section, then one bullet per changed area. Explain why this approach
   over the alternative you considered, and what you deliberately did not do.
   A ticket link may follow prose; a bare link never replaces it.
3. **Testing with named commands.** "Tested locally" is not testing. Name the
   exact commands, suites, and files you ran, the environment you ran them in,
   and the edge cases you checked. State what you did **not** test and the risk
   it carries — untested paths are the first thing a reviewer needs to weigh.
4. **Reviewer notes.** Say where to start reading, which spots are risky, and
   which design decisions deserve scrutiny. Flag anything unconventional
   explicitly; one sentence about a deliberate oddity prevents a long comment
   thread.
5. **Screenshots and links when they carry information.** UI changes get a
   before/after pair; CLI output and plan results can go in a collapsible
   `<details>` block. Keep issue links that the body already carries.
6. **Length discipline.** Roughly 50 to 100 words for a typo-class fix, 150 to
   250 for a feature, 300 to 400 for a multi-component change. Short
   paragraphs, bullets over prose walls, and caveats near the top — never
   buried in the last line.
7. **Plain language.** Active voice, complete sentences, no marketing
   adjectives on your own code, no acronym soup. You are writing to one person
   under time pressure, not composing documentation.

## Anti-patterns

Any of these means rewrite before posting:

- "See #123", "See the subject", "Bob knows about this"
- "Fixed stuff", "Updated logic", "Various improvements"
- "Tested locally" with nothing named
- Implementation detail before the reason the change exists
- A known limitation appearing only in the last line
- Marketing tone ("blazing fast", "much cleaner") about your own change

## Checklist before posting

- [ ] A cold reader can state the problem after the first paragraph
- [ ] Every changed area is named with a real file or symbol
- [ ] The testing section names commands a reviewer could re-run
- [ ] Untested paths and their risks are stated
- [ ] Reviewer notes name a starting point and the risky spots
- [ ] No section is a bare link; issues are linked but explained

## Template

Paste and fill in; delete sections that do not carry weight for this change.

```markdown
## Motivation

<The problem, with the context a maintainer who does not know this fork
needs. What was broken, slow, or missing before this change. One or two
short paragraphs, then the issue link if one exists.>

## Changes

<Primary change in the first sentence; then one bullet per changed area,
naming real files and symbols from the diff.>

- `path/to/file.ts` — what changed there and why

<Why this approach over the alternative; what was deliberately left out.>

## Testing

<Named commands and suites, in the environment you ran them.>

- `command you ran` — what it proved

Untested: <what, why, and the risk it carries.>

## Reviewer notes

<Where to start reading; risky spots; decisions worth scrutiny; anything
unconventional.>

## Screenshots

<Only when the change is visible: before/after for UI, a capture for CLI
output. Delete this section otherwise.>
```
